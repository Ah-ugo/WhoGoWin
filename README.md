# 🧠 Odin Games – Lottery Backend (FastAPI)

This is the backend for **Odin Games’ digital lottery app**, powering draws, ticket purchases, winner selection, payouts, notifications, and more. Built with **FastAPI**, **MongoDB**, and **Cloudinary**, the system is designed to be scalable, secure, and API-first.

---

## 🚀 Features

- 🔐 **User Authentication**
  - Register, login, and verify users
  - JWT-based access token system
  - Role-based access control (User, Admin)

- 🎟️ **Lottery System**
  - Create and manage draw rounds
  - Buy tickets with unique numbers
  - Scheduled draw closing and winner selection
  - 1st Place: 50% of prize pool
  - Consolation (others who matched partially): 10% shared
  - Odin Games (platform): 40% retained

- 💸 **Payments**
  - Integrate with payment processors (Paystack)
  - Handle ticket payments
  - Admin and user wallet support (MongoDB + transaction records)

- 🔔 **Notification System**
  - Push notifications (Expo push )




---


