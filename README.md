### Technology Stack

- **Backend:** Python, Flask  
- **Real-Time Communication:** WebSockets  
- **Frontend:** HTML, CSS, JavaScript  
- **Database:** SQL  
- **Deployment:** AWS EC2 (with Elastic IP), Gunicorn (WSGI server)  

---

### Deployment

The Bingo game was deployed on AWS EC2 using **Gunicorn** as the WSGI server to run the Flask application.  
The app was started with the command:  

```bash
gunicorn app:app --bind 0.0.0.0:8000
