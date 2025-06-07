from fastapi import APIRouter, HTTPException, status, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
import secrets
import string
import os
from fastapi.responses import HTMLResponse
from models.user import UserCreate, UserLogin, TokenResponse, UserResponse, Role, ForgotPasswordRequest, ResetPasswordRequest
from database import users_collection
from bson import ObjectId
from services.email_service import send_email

router = APIRouter()
security = HTTPBearer()

# Security
SECRET_KEY = os.getenv("SECRET_KEY", "your-secret-key-here")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30 * 24 * 60  # 30 days
RESET_TOKEN_EXPIRE_MINUTES = 60

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

def verify_password(plain_password, hashed_password):
    return pwd_context.verify(plain_password, hashed_password)

def get_password_hash(password):
    return pwd_context.hash(password)

def create_access_token(data: dict, expires_delta: timedelta = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def generate_referral_code():
    """Generate a unique referral code"""
    return ''.join(secrets.choice(string.ascii_uppercase + string.digits) for _ in range(8))

def generate_reset_token():
    """Generate a secure random reset token"""
    return ''.join(secrets.choice(string.ascii_letters + string.digits) for _ in range(32))

async def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)):
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
        user_id: str = payload.get("sub")
        if user_id is None:
            raise credentials_exception
    except JWTError:
        raise credentials_exception

    user = await users_collection.find_one({"_id": ObjectId(user_id)})
    if user is None:
        raise credentials_exception

    return user

async def get_current_admin_user(current_user: dict = Depends(get_current_user)):
    if current_user.get("role") != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Admin access required"
        )
    return current_user

@router.post("/register", response_model=TokenResponse)
async def register(user_data: UserCreate):
    # Check if user already exists
    existing_user = await users_collection.find_one({"email": user_data.email})
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )

    # Generate unique referral code
    referral_code = generate_referral_code()
    while await users_collection.find_one({"referral_code": referral_code}):
        referral_code = generate_referral_code()

    # Create user with default 'user' role
    hashed_password = get_password_hash(user_data.password)
    user_doc = {
        "name": user_data.name,
        "email": user_data.email,
        "password": hashed_password,
        "role": Role.USER,
        "referral_code": referral_code,
        "wallet_balance": 0.0,
        "total_referrals": 0,
        "created_at": datetime.utcnow(),
        "is_active": True
    }

    result = await users_collection.insert_one(user_doc)
    user_doc["_id"] = result.inserted_id

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(result.inserted_id)}, expires_delta=access_token_expires
    )

    user_response = UserResponse(
        id=str(user_doc["_id"]),
        name=user_doc["name"],
        email=user_doc["email"],
        role=user_doc["role"],
        referral_code=user_doc["referral_code"],
        wallet_balance=user_doc["wallet_balance"],
        total_referrals=user_doc["total_referrals"],
        created_at=user_doc["created_at"]
    )

    return TokenResponse(access_token=access_token, user=user_response)

@router.post("/login", response_model=TokenResponse)
async def login(user_data: UserLogin):
    user = await users_collection.find_one({"email": user_data.email})
    if not user or not verify_password(user_data.password, user["password"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password"
        )

    if not user.get("is_active", True):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Account is deactivated"
        )

    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user["_id"])}, expires_delta=access_token_expires
    )

    user_response = UserResponse(
        id=str(user["_id"]),
        name=user["name"],
        email=user["email"],
        role=user["role"],
        referral_code=user["referral_code"],
        wallet_balance=user.get("wallet_balance", 0.0),
        total_referrals=user.get("total_referrals", 0),
        created_at=user["created_at"]
    )

    return TokenResponse(access_token=access_token, user=user_response)


@router.post("/forgot-password")
async def forgot_password(request: ForgotPasswordRequest):
    # Find user by email
    user = await users_collection.find_one({"email": request.email})
    if not user:
        # Return success even if user doesn't exist to prevent email enumeration
        return {"message": "If an account exists, a reset link has been sent"}

    # Generate reset token and expiration
    reset_token = generate_reset_token()
    reset_token_expires = datetime.utcnow() + timedelta(minutes=RESET_TOKEN_EXPIRE_MINUTES)

    # Store reset token and expiration in user document
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {
                "reset_token": reset_token,
                "reset_token_expires": reset_token_expires
            }
        }
    )

    # Create reset link (replace with your frontend URL)
    reset_link = f"https://whogowin.onrender.com/api/v1/auth/reset-password?token={reset_token}"

    # Send email with reset link
    subject = "Password Reset Request"
    body = f"""
    <h2>Password Reset Request</h2>
    <p>You requested to reset your password. Click the link below to set a new password:</p>
    <p><a href="{reset_link}">Reset Password</a></p>
    <p>This link will expire in {RESET_TOKEN_EXPIRE_MINUTES} minutes.</p>
    <p>If you didn't request this, please ignore this email.</p>
    """
    await send_email(to_email=request.email, subject=subject, body=body)

    return {"message": "If an account exists, a reset link has been sent"}

@router.post("/reset-password")
async def reset_password(request: ResetPasswordRequest):
    # Find user by reset token
    user = await users_collection.find_one({"reset_token": request.token})
    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Check if token has expired
    if user.get("reset_token_expires") < datetime.utcnow():
        # Clear expired token
        await users_collection.update_one(
            {"_id": user["_id"]},
            {"$unset": {"reset_token": "", "reset_token_expires": ""}}
        )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired reset token"
        )

    # Update password and clear reset token
    hashed_password = get_password_hash(request.new_password)
    await users_collection.update_one(
        {"_id": user["_id"]},
        {
            "$set": {"password": hashed_password},
            "$unset": {"reset_token": "", "reset_token_expires": ""}
        }
    )

    return {"message": "Password reset successfully"}


@router.get("/reset-password", response_class=HTMLResponse)
async def reset_password_page():
    """
    Serve the HTML interface for resetting the password.
    """
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Reset Password - WhoGoWin</title>
        <script src="https://cdn.tailwindcss.com"></script>
        <style>
            .error { color: #ef4444; }
            .success { color: #10b981; }
            .hidden { display: none; }
        </style>
    </head>
    <body class="bg-gray-900 min-h-screen flex items-center justify-center px-4 sm:px-6 lg:px-8">
        <div class="w-full max-w-md bg-gray-800 p-6 sm:p-8 rounded-lg shadow-lg">
            <h2 class="text-2xl sm:text-3xl font-bold text-white text-center mb-6">Reset Your Password</h2>
            <div id="message" class="mb-4 text-center text-sm sm:text-base hidden"></div>
            <form id="reset-password-form" class="space-y-6">
                <div>
                    <label for="password" class="block text-sm font-medium text-gray-300">New Password</label>
                    <input type="password" id="password" name="password" required
                           class="mt-1 w-full px-3 py-2 bg-gray-700 text-white border border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-yellow-500 text-sm sm:text-base"
                           placeholder="Enter new password">
                </div>
                <div>
                    <label for="confirm-password" class="block text-sm font-medium text-gray-300">Confirm Password</label>
                    <input type="password" id="confirm-password" name="confirm-password" required
                           class="mt-1 w-full px-3 py-2 bg-gray-700 text-white border border-gray-600 rounded-md focus:outline-none focus:ring-2 focus:ring-yellow-500 text-sm sm:text-base"
                           placeholder="Confirm new password">
                </div>
                <button type="submit"
                        class="w-full bg-yellow-500 text-gray-900 font-semibold py-2 px-4 rounded-md hover:bg-yellow-400 transition duration-200 text-sm sm:text-base">
                    Reset Password
                </button>
            </form>
            <p class="mt-4 text-center text-sm text-gray-400">
                After resetting, return to the WhoGoWin mobile app to log in.
            </p>
        </div>

        <script>
            document.getElementById('reset-password-form').addEventListener('submit', async (e) => {
                e.preventDefault();

                const password = document.getElementById('password').value;
                const confirmPassword = document.getElementById('confirm-password').value;
                const messageDiv = document.getElementById('message');

                // Client-side validation
                if (password !== confirmPassword) {
                    messageDiv.className = 'error';
                    messageDiv.textContent = 'Passwords do not match';
                    messageDiv.classList.remove('hidden');
                    return;
                }

                // Get token from URL
                const urlParams = new URLSearchParams(window.location.search);
                const token = urlParams.get('token');
                if (!token) {
                    messageDiv.className = 'error';
                    messageDiv.textContent = 'Invalid or missing reset token';
                    messageDiv.classList.remove('hidden');
                    return;
                }

                // Disable button during request
                const button = document.querySelector('button[type="submit"]');
                button.disabled = true;
                button.textContent = 'Resetting...';

                try {
                    const response = await fetch('https://whogowin.onrender.com/api/v1/auth/reset-password', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify({ token, new_password: password })
                    });

                    const data = await response.json();
                    if (response.ok) {
                        messageDiv.className = 'success';
                        messageDiv.textContent = 'Password reset successfully. Please return to the WhoGoWin mobile app to log in.';
                        messageDiv.classList.remove('hidden');
                        // No redirect since it's a mobile app
                    } else {
                        messageDiv.className = 'error';
                        messageDiv.textContent = data.detail || 'Failed to reset password';
                        messageDiv.classList.remove('hidden');
                    }
                } catch (error) {
                    messageDiv.className = 'error';
                    messageDiv.textContent = 'An error occurred. Please try again.';
                    messageDiv.classList.remove('hidden');
                } finally {
                    button.disabled = false;
                    button.textContent = 'Reset Password';
                }
            });
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)