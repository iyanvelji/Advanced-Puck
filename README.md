**Live Site:** [https://advancedpuck.com](https://advancedpuck.com)

Advanced Puck is a free NHL hockey analytics web application featuring live tandings, skater leaderboards, goalie leaderboards, and detailed team and player analytics powered by the NHL API and MoneyPuck.

---

## Languages Used

* **TypeScript**
* **Python**
* **CSS** 
* **HTML**
* **SQL (PostgreSQL)**

---

## Run locally

### 1. Backend (Django)

```bash
cd backend
python -m venv venv
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### 2. Frontend (React + Vite)

```bash
cd frontend
npm install
npm run dev
```

The frontend runs locally at `http://localhost:5173`.

---

## Support Advanced Puck

Advanced Puck is free for everyone to use. If you find the site helpful and want to help cover hosting and maintenance costs, you can support the project on Ko-fi:

**[https://ko-fi.com/advancedpuck](https://ko-fi.com/advancedpuck)**
