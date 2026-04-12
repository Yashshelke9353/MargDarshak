# 🧭 Marg Darshak (मार्गदर्शक)

<div align="center">

![Marg Darshak Logo](https://img.shields.io/badge/Marg-Darshak-blue?style=for-the-badge&logo=compass)

**"जीवन के हर पड़ाव पर सही दिशा"**  
*Finding Your Path in Life*


</div>

---

## 📖 About

**Marg Darshak** is a comprehensive web-based platform that combines three essential guidance systems into one unified experience:

1. **🎯 Career Compass** - AI-powered career recommendation system
2. **📿 Gyan Kosh (ज्ञान कोश)** - Digital repository of spiritual wisdom
3. **📚 Skill Saathi** - Curated learning resources aggregator

Built as a **minor project** for college, this platform addresses the real challenges students face: career confusion, lack of accessible wisdom, and scattered learning resources.

---

## ✨ Features

### 🎯 Career Compass
- **Interactive Quiz**: Personality-based questionnaire to identify career interests
- **ML-Powered Recommendations**: Machine learning algorithms analyze responses
- **Detailed Roadmaps**: Step-by-step career paths with skills, colleges, and salary info
- **Browse 25+ Careers**: Technology, Business, Creative, Healthcare, and more

### 📿 Gyan Kosh (ज्ञान कोश)
- **Daily Wisdom**: Random verse from Bhagavad Gita displayed daily
- **Multi-language Support**: Sanskrit, Hindi, and English
- **Practical Applications**: Modern-life context for ancient wisdom
- **Search Functionality**: Find verses by topic, keyword, or theme
- **Audio Support**: Links to Sanskrit recitations

### 📚 Skill Saathi
- **Resource Aggregation**: YouTube, Coursera, Udemy, and more
- **Quality Ratings**: User-reviewed content scoring
- **Smart Filters**: By topic, difficulty, platform, and price
- **30+ Curated Resources**: Hand-picked quality content

### 🎨 Additional Features
- ✅ **Dark Mode**: Eye-friendly theme toggle
- ✅ **Responsive Design**: Works on mobile, tablet, and desktop
- ✅ **Sidebar Navigation**: Easy access to all features
- ✅ **Progress Tracking**: Quiz progress saved in browser
- ✅ **Share Functionality**: Share career recommendations
- ✅ **Data Visualization**: Interactive charts and graphs

---

## 🛠️ Tech Stack

### Backend
- **Python 3.9+**
- **Flask 3.0** - Web framework
- **SQLite** - Database
- **Pandas** - Data manipulation
- **NumPy** - Numerical operations
- **Scikit-learn** - Machine learning

### Frontend
- **HTML5, CSS3, JavaScript**
- **Bootstrap 5** - UI framework
- **Font Awesome** - Icons
- **Plotly.js** - Data visualization
- **Matplotlib/Seaborn** - Charts

### Data Science
- **ML Classification** - Career recommendation engine
- **NLP** - Text analysis for spiritual content
- **Statistical Analysis** - Data insights

### Deployment
- **Render** - Cloud hosting
- **Git/GitHub** - Version control

---

## 🚀 Getting Started

### Prerequisites
```bash
Python 3.9+
pip (Python package manager)
Git
```

### Installation

1. **Clone the repository**
```bash
cd marg-darshak
```

2. **Create virtual environment**
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

3. **Install dependencies**
```bash
pip install -r requirements.txt
```

4. **Initialize database**
```bash
python database/init_db.py
python database/load_csv_to_db.py
```

5. **Run the application**
```bash
python app.py
```

6. **Open in browser**
```
http://localhost:5000
```

---

## 📂 Project Structure
```
marg-darshak/
├── app.py                      # Main Flask application
├── requirements.txt            # Python dependencies
├── README.md                   # This file
│
├── database/
│   ├── init_db.py             # Database initialization
│   ├── load_csv_to_db.py      # Data loader
│   └── marg_darshak.db        # SQLite database
│
├── data/
│   ├── careers.csv            # Career data
│   ├── shlokas.csv            # Spiritual verses
│   └── resources.csv          # Learning resources
│
├── templates/
│   ├── base.html              # Base template
│   ├── index.html             # Homepage
│   ├── career/                # Career module templates
│   ├── gyan/                  # Gyan Kosh templates
│   └── skill/                 # Skill Saathi templates
│
├── static/
│   ├── css/                   # Stylesheets
│   ├── js/                    # JavaScript files
│   └── images/                # Images and icons
│
└── models/
    └── career_model.py        # ML model (future)
```

---

## 📊 Database Schema

### Careers Table
```sql
- id (Primary Key)
- title, category, description
- required_skills, avg_salary_inr
- growth_rate, difficulty_level
- education_required, top_colleges, job_roles
```

### Gyan Kosh Table
```sql
- id (Primary Key)
- source, chapter, verse_number
- sanskrit_text, hindi_meaning, english_meaning
- practical_application, tags, audio_url
```

### Learning Resources Table
```sql
- id (Primary Key)
- title, topic, platform, resource_type
- url, difficulty, duration_hours
- quality_score, language, is_free
```

---

## 🎯 How It Works

### Career Recommendation Algorithm

1. **User takes quiz** (3 questions on interests, work style, environment)
2. **Responses categorized** into 5 categories:
   - Technical
   - Creative
   - Social
   - Analytical
   - Entrepreneurial
3. **Scoring system** counts frequency of each category
4. **ML classification** matches to career database
5. **Top 5 careers** recommended with detailed info

### Data Flow
```
User Input → Flask Backend → SQLite Database → 
ML Processing → JSON Response → Frontend Display
```

---

## 🤝 Contributing

This is a college project, but contributions are welcome!

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

---

## 💡 Future Enhancements

- [ ] User authentication and profiles
- [ ] Advanced ML models (Neural Networks)
- [ ] More spiritual texts (Upanishads, Ramayana)
- [ ] Video course integration
- [ ] Mobile app (React Native)
- [ ] Community forum
- [ ] Mentor matching system
- [ ] Career counselor dashboard
- [ ] API for third-party integration

---

## 🐛 Known Issues

- Page loader sometimes gets stuck (workaround: hard refresh)
- Audio links redirect to YouTube search (intentional for privacy)
- Limited to 25 careers (expanding soon)

</div>

---

## 🙏 Acknowledgments

- **AI Assistance**: Built with guidance from Claude AI and ChatGPT for debugging, optimization, and best practices
- **Data Sources**: 
  - Career data from Wikipedia, government portals
  - Bhagavad Gita verses from public domain sources
  - Learning resources curated from YouTube, Coursera, Udemy, ai
- **College**: [Matoshri College of engineering Nashik ] - Major Project
- **Inspiration**: Personal struggle with career decisions

---

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

---

## 👨‍💻 Author

**Yash Shelke**
---

<div align="center">

**⭐ If this project helped you, please give it a star! ⭐**

Made with ❤️ by Yash Shelke

</div>
