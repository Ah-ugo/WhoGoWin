from fastapi import FastAPI, HTTPException, Depends, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from contextlib import asynccontextmanager
import uvicorn
from datetime import datetime, timedelta
import asyncio
import os
from dotenv import load_dotenv

from routes import auth, users, draws, tickets, wallet, notifications
from database import init_db
from services.draw_service import DrawService
from services.notification_service import NotificationService

load_dotenv()

# Initialize services
draw_service = DrawService()
notification_service = NotificationService()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    await init_db()

    # Start background tasks
    asyncio.create_task(draw_service.start_draw_scheduler())
    asyncio.create_task(notification_service.start_notification_scheduler())

    yield

    # Shutdown
    pass


app = FastAPI(
    title="WhoGoWin Lottery API",
    description="WhoGoWin Lottery API",
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Configure appropriately for production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(auth.router, prefix="/api/v1/auth", tags=["Authentication"])
app.include_router(users.router, prefix="/api/v1/users", tags=["Users"])
app.include_router(draws.router, prefix="/api/v1/draws", tags=["Draws"])
app.include_router(tickets.router, prefix="/api/v1/tickets", tags=["Tickets"])
app.include_router(wallet.router, prefix="/api/v1/wallet", tags=["Wallet"])
app.include_router(notifications.router, prefix="/api/v1/notifications", tags=["Notifications"])




@app.get("/", response_class=HTMLResponse)
async def root():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>WhoGoWin - ₦100 Fit Change Your Life</title>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://cdnjs.cloudflare.com/ajax/libs/aos/2.3.4/aos.js"></script>
    <link href="https://cdnjs.cloudflare.com/ajax/libs/aos/2.3.4/aos.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css" rel="stylesheet">
    <style>
        :root {
            --primary-dark: #0a0a0a;
            --primary-gold: #d4af37;
        }

        .gradient-bg {
            background: linear-gradient(135deg, var(--primary-dark) 0%, #1a1a2e 50%, var(--primary-dark) 100%);
        }

        .gold-gradient {
            background: linear-gradient(135deg, var(--primary-gold) 0%, #ffd700 50%, var(--primary-gold) 100%);
        }

        .floating {
            animation: float 6s ease-in-out infinite;
        }

        .floating-delayed {
            animation: float 6s ease-in-out infinite;
            animation-delay: -3s;
        }

        @keyframes float {
            0%, 100% { transform: translateY(0px); }
            50% { transform: translateY(-20px); }
        }

        .pulse-glow {
            animation: pulseGlow 2s ease-in-out infinite alternate;
        }

        @keyframes pulseGlow {
            from { box-shadow: 0 0 20px rgba(212, 175, 55, 0.3); }
            to { box-shadow: 0 0 40px rgba(212, 175, 55, 0.6); }
        }

        .money-fall {
            position: absolute;
            font-size: 2rem;
            color: var(--primary-gold);
            animation: fall 4s linear infinite;
            opacity: 0.7;
        }

        @keyframes fall {
            0% { transform: translateY(-100vh) rotate(0deg); opacity: 1; }
            100% { transform: translateY(100vh) rotate(360deg); opacity: 0; }
        }

        .hover-lift {
            transition: all 0.3s ease;
        }

        .hover-lift:hover {
            transform: translateY(-5px);
            box-shadow: 0 10px 25px rgba(212, 175, 55, 0.3);
        }

        .text-shadow {
            text-shadow: 2px 2px 4px rgba(0,0,0,0.5);
        }

        .card-glow {
            background: rgba(255, 255, 255, 0.05);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(212, 175, 55, 0.2);
        }

        .step-number {
            background: linear-gradient(135deg, var(--primary-gold), #ffd700);
            background-clip: text;
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
        }
    </style>
</head>
<body class="bg-gray-900 text-white overflow-x-hidden">
    <!-- Floating Money Animation -->
    <div class="fixed inset-0 pointer-events-none z-0">
        <div class="money-fall" style="left: 10%; animation-delay: 0s;">₦</div>
        <div class="money-fall" style="left: 20%; animation-delay: 1s;">₦</div>
        <div class="money-fall" style="left: 30%; animation-delay: 2s;">₦</div>
        <div class="money-fall" style="left: 40%; animation-delay: 0.5s;">₦</div>
        <div class="money-fall" style="left: 50%; animation-delay: 1.5s;">₦</div>
        <div class="money-fall" style="left: 60%; animation-delay: 2.5s;">₦</div>
        <div class="money-fall" style="left: 70%; animation-delay: 0.8s;">₦</div>
        <div class="money-fall" style="left: 80%; animation-delay: 1.8s;">₦</div>
        <div class="money-fall" style="left: 90%; animation-delay: 3s;">₦</div>
    </div>

    <!-- Hero Section -->
    <section class="gradient-bg relative min-h-screen flex items-center justify-center px-4 py-20">
        <div class="container mx-auto text-center relative z-10">
            <div class="floating mb-8">
                <h1 class="text-6xl md:text-8xl font-bold mb-4 text-shadow" style="color: var(--primary-gold);" data-aos="fade-up">
                    WhoGoWin
                </h1>
                <div class="w-24 h-1 gold-gradient mx-auto mb-6" data-aos="fade-up" data-aos-delay="200"></div>
            </div>

            <div class="floating-delayed" data-aos="fade-up" data-aos-delay="400">
                <h2 class="text-3xl md:text-5xl font-bold mb-6 text-shadow">
                    ₦100 Fit Change Your Life
                </h2>
                <p class="text-xl md:text-2xl mb-8 max-w-3xl mx-auto text-gray-300">
                    Nigeria's most trusted digital lottery platform. Buy tickets in under 1 minute, win big every week!
                </p>
            </div>

            <div class="space-y-4 md:space-y-0 md:space-x-6 md:flex md:justify-center md:items-center" data-aos="fade-up" data-aos-delay="600">
                <button class="gold-gradient hover-lift pulse-glow px-8 py-4 rounded-full text-black font-bold text-xl transition-all duration-300 w-full md:w-auto">
                    <i class="fas fa-download mr-2"></i>
                    Download App Now
                </button>
                <button class="border-2 border-yellow-400 text-yellow-400 hover:bg-yellow-400 hover:text-black px-8 py-4 rounded-full font-bold text-xl transition-all duration-300 w-full md:w-auto">
                    <i class="fas fa-play mr-2"></i>
                    Watch Demo
                </button>
            </div>

            <div class="mt-12 grid grid-cols-1 md:grid-cols-3 gap-6 max-w-4xl mx-auto" data-aos="fade-up" data-aos-delay="800">
                <div class="card-glow rounded-xl p-6 hover-lift">
                    <div class="text-4xl font-bold" style="color: var(--primary-gold);">₦10M+</div>
                    <div class="text-gray-300">Total Winnings</div>
                </div>
                <div class="card-glow rounded-xl p-6 hover-lift">
                    <div class="text-4xl font-bold" style="color: var(--primary-gold);">50K+</div>
                    <div class="text-gray-300">Happy Winners</div>
                </div>
                <div class="card-glow rounded-xl p-6 hover-lift">
                    <div class="text-4xl font-bold" style="color: var(--primary-gold);">100%</div>
                    <div class="text-gray-300">Secure & Fair</div>
                </div>
            </div>
        </div>
    </section>

    <!-- How It Works Section -->
    <section class="py-20 px-4 bg-gray-800">
        <div class="container mx-auto">
            <div class="text-center mb-16" data-aos="fade-up">
                <h2 class="text-4xl md:text-6xl font-bold mb-4" style="color: var(--primary-gold);">How It Works</h2>
                <p class="text-xl text-gray-300 max-w-2xl mx-auto">Getting started is simple. Follow these 3 easy steps to join thousands of winners!</p>
            </div>

            <div class="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="200">
                    <div class="w-20 h-20 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6 text-4xl font-bold text-black">
                        1
                    </div>
                    <h3 class="text-2xl font-bold mb-4" style="color: var(--primary-gold);">Buy Ticket Online</h3>
                    <p class="text-gray-300 text-lg">Purchase your lottery ticket with just ₦100 using your phone. Quick, easy, and secure payment options.</p>
                    <div class="mt-6">
                        <i class="fas fa-mobile-alt text-6xl" style="color: var(--primary-gold);"></i>
                    </div>
                </div>

                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="400">
                    <div class="w-20 h-20 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6 text-4xl font-bold text-black">
                        2
                    </div>
                    <h3 class="text-2xl font-bold mb-4" style="color: var(--primary-gold);">Wait for Weekly Draw</h3>
                    <p class="text-gray-300 text-lg">Our automated system conducts fair draws weekly, daily, and monthly. All results are transparent and verifiable.</p>
                    <div class="mt-6">
                        <i class="fas fa-calendar-alt text-6xl" style="color: var(--primary-gold);"></i>
                    </div>
                </div>

                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="600">
                    <div class="w-20 h-20 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6 text-4xl font-bold text-black">
                        3
                    </div>
                    <h3 class="text-2xl font-bold mb-4" style="color: var(--primary-gold);">Win & Get Paid</h3>
                    <p class="text-gray-300 text-lg">Winners receive instant notifications and payments directly to their bank accounts. No delays, no hassles!</p>
                    <div class="mt-6">
                        <i class="fas fa-trophy text-6xl" style="color: var(--primary-gold);"></i>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Benefits Section -->
    <section class="py-20 px-4 gradient-bg">
        <div class="container mx-auto">
            <div class="text-center mb-16" data-aos="fade-up">
                <h2 class="text-4xl md:text-6xl font-bold mb-4" style="color: var(--primary-gold);">Why Choose WhoGoWin?</h2>
                <p class="text-xl text-gray-300 max-w-2xl mx-auto">Experience the most trusted and rewarding lottery platform in Nigeria</p>
            </div>

            <div class="grid md:grid-cols-2 lg:grid-cols-4 gap-8 max-w-6xl mx-auto">
                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="200">
                    <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6">
                        <i class="fas fa-shield-alt text-2xl text-black"></i>
                    </div>
                    <h3 class="text-xl font-bold mb-4" style="color: var(--primary-gold);">Safe & Secure</h3>
                    <p class="text-gray-300">Bank-level security with encrypted transactions and verified payment systems.</p>
                </div>

                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="400">
                    <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6">
                        <i class="fas fa-clock text-2xl text-black"></i>
                    </div>
                    <h3 class="text-xl font-bold mb-4" style="color: var(--primary-gold);">Multiple Draws</h3>
                    <p class="text-gray-300">Weekly, daily, and monthly draws give you more chances to win big prizes.</p>
                </div>

                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="600">
                    <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6">
                        <i class="fas fa-bolt text-2xl text-black"></i>
                    </div>
                    <h3 class="text-xl font-bold mb-4" style="color: var(--primary-gold);">Fast Payment</h3>
                    <p class="text-gray-300">Instant payouts directly to your bank account. No waiting, no complications.</p>
                </div>

                <div class="text-center card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="800">
                    <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center mx-auto mb-6">
                        <i class="fas fa-users text-2xl text-black"></i>
                    </div>
                    <h3 class="text-xl font-bold mb-4" style="color: var(--primary-gold);">Invite & Earn</h3>
                    <p class="text-gray-300">Get free tickets by inviting friends. The more you share, the more you earn!</p>
                </div>
            </div>
        </div>
    </section>

    <!-- Testimonials Section -->
    <section class="py-20 px-4 bg-gray-800">
        <div class="container mx-auto">
            <div class="text-center mb-16" data-aos="fade-up">
                <h2 class="text-4xl md:text-6xl font-bold mb-4" style="color: var(--primary-gold);">Happy Winners</h2>
                <p class="text-xl text-gray-300 max-w-2xl mx-auto">Real people, real wins, real life changes</p>
            </div>

            <div class="grid md:grid-cols-3 gap-8 max-w-6xl mx-auto">
                <div class="card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="200">
                    <div class="flex items-center mb-6">
                        <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center text-2xl font-bold text-black mr-4">
                            A
                        </div>
                        <div>
                            <h4 class="font-bold text-xl" style="color: var(--primary-gold);">Adaora O.</h4>
                            <p class="text-gray-400">Lagos State</p>
                        </div>
                    </div>
                    <p class="text-gray-300 text-lg mb-4">"I won ₦500,000 with just ₦100! WhoGoWin changed my life. I used the money to start my business and now I'm financially independent."</p>
                    <div class="flex text-yellow-400">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                    </div>
                </div>

                <div class="card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="400">
                    <div class="flex items-center mb-6">
                        <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center text-2xl font-bold text-black mr-4">
                            E
                        </div>
                        <div>
                            <h4 class="font-bold text-xl" style="color: var(--primary-gold);">Emeka C.</h4>
                            <p class="text-gray-400">Abuja</p>
                        </div>
                    </div>
                    <p class="text-gray-300 text-lg mb-4">"The app is so easy to use! I've won multiple times and the payment is always instant. My friends and I play together every week now."</p>
                    <div class="flex text-yellow-400">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                    </div>
                </div>

                <div class="card-glow rounded-2xl p-8 hover-lift" data-aos="fade-up" data-aos-delay="600">
                    <div class="flex items-center mb-6">
                        <div class="w-16 h-16 rounded-full gold-gradient flex items-center justify-center text-2xl font-bold text-black mr-4">
                            F
                        </div>
                        <div>
                            <h4 class="font-bold text-xl" style="color: var(--primary-gold);">Funmi S.</h4>
                            <p class="text-gray-400">Ibadan</p>
                        </div>
                    </div>
                    <p class="text-gray-300 text-lg mb-4">"I was skeptical at first, but WhoGoWin proved me wrong. I won ₦250,000 last month and paid my children's school fees. Thank you!"</p>
                    <div class="flex text-yellow-400">
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                        <i class="fas fa-star"></i>
                    </div>
                </div>
            </div>
        </div>
    </section>

    <!-- Final CTA Section -->
    <section class="py-20 px-4 gradient-bg text-center">
        <div class="container mx-auto" data-aos="fade-up">
            <h2 class="text-4xl md:text-6xl font-bold mb-6" style="color: var(--primary-gold);">
                Ready to Change Your Life?
            </h2>
            <p class="text-xl md:text-2xl mb-8 max-w-3xl mx-auto text-gray-300">
                Join thousands of Nigerians who are already winning with WhoGoWin. Your lucky numbers are waiting!
            </p>
            <button class="gold-gradient hover-lift pulse-glow px-12 py-6 rounded-full text-black font-bold text-2xl transition-all duration-300">
                <i class="fas fa-download mr-3"></i>
                Download WhoGoWin Now
            </button>
            <p class="mt-4 text-sm text-gray-400">Available on Android and iOS • 100% Free to Download</p>
        </div>
    </section>

    <!-- Footer -->
    <footer class="bg-black py-12 px-4">
        <div class="container mx-auto">
            <div class="grid md:grid-cols-4 gap-8 mb-8">
                <div>
                    <h3 class="text-2xl font-bold mb-4" style="color: var(--primary-gold);">WhoGoWin</h3>
                    <p class="text-gray-400 mb-4">Nigeria's most trusted digital lottery platform. Fair, secure, and transparent.</p>
                    <div class="flex space-x-4">
                        <a href="#" class="text-2xl hover:text-yellow-400 transition-colors">
                            <i class="fab fa-facebook"></i>
                        </a>
                        <a href="#" class="text-2xl hover:text-yellow-400 transition-colors">
                            <i class="fab fa-twitter"></i>
                        </a>
                        <a href="#" class="text-2xl hover:text-yellow-400 transition-colors">
                            <i class="fab fa-instagram"></i>
                        </a>
                        <a href="#" class="text-2xl hover:text-yellow-400 transition-colors">
                            <i class="fab fa-whatsapp"></i>
                        </a>
                    </div>
                </div>

                <div>
                    <h4 class="text-lg font-bold mb-4" style="color: var(--primary-gold);">Quick Links</h4>
                    <ul class="space-y-2 text-gray-400">
                        <li><a href="#" class="hover:text-white transition-colors">How It Works</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">Winners</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">FAQ</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">Terms & Conditions</a></li>
                    </ul>
                </div>

                <div>
                    <h4 class="text-lg font-bold mb-4" style="color: var(--primary-gold);">Support</h4>
                    <ul class="space-y-2 text-gray-400">
                        <li><a href="#" class="hover:text-white transition-colors">Help Center</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">Contact Us</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">Privacy Policy</a></li>
                        <li><a href="#" class="hover:text-white transition-colors">Security</a></li>
                    </ul>
                </div>

                <div>
                    <h4 class="text-lg font-bold mb-4" style="color: var(--primary-gold);">Contact Info</h4>
                    <div class="space-y-2 text-gray-400">
                        <p><i class="fas fa-envelope mr-2"></i>info@whogowin.ng</p>
                        <p><i class="fas fa-phone mr-2"></i>+234 800 WHO GOWIN</p>
                        <p><i class="fas fa-map-marker-alt mr-2"></i>Lagos, Nigeria</p>
                    </div>
                </div>
            </div>

            <div class="border-t border-gray-800 pt-8 flex flex-col md:flex-row justify-between items-center">
                <p class="text-gray-400 mb-4 md:mb-0">© 2025 WhoGoWin. All rights reserved.</p>
                <p class="text-gray-400 text-sm">Powered by Odin Games</p>
            </div>
        </div>
    </footer>

    <script>
        // Initialize AOS
        AOS.init({
            duration: 1000,
            once: true,
            offset: 100
        });

        // Smooth scrolling for anchor links
        document.querySelectorAll('a[href^="#"]').forEach(anchor => {
            anchor.addEventListener('click', function (e) {
                e.preventDefault();
                document.querySelector(this.getAttribute('href')).scrollIntoView({
                    behavior: 'smooth'
                });
            });
        });

        // Add some interactive elements
        document.querySelectorAll('button').forEach(button => {
            button.addEventListener('click', function(e) {
                // Create ripple effect
                const ripple = document.createElement('span');
                const rect = this.getBoundingClientRect();
                const size = Math.max(rect.width, rect.height);
                const x = e.clientX - rect.left - size / 2;
                const y = e.clientY - rect.top - size / 2;

                ripple.style.width = ripple.style.height = size + 'px';
                ripple.style.left = x + 'px';
                ripple.style.top = y + 'px';
                ripple.classList.add('ripple');

                this.appendChild(ripple);

                setTimeout(() => {
                    ripple.remove();
                }, 600);
            });
        });

        // Add CSS for ripple effect
        const style = document.createElement('style');
        style.textContent = `
            .ripple {
                position: absolute;
                border-radius: 50%;
                background: rgba(255, 255, 255, 0.3);
                animation: ripple-animation 0.6s linear;
                pointer-events: none;
            }

            @keyframes ripple-animation {
                to {
                    transform: scale(2);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    </script>
</body>
</html>
    """


@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.utcnow()}


if __name__ == "__main__":
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=True
    )
