### Deployment

The Bingo game was deployed on AWS EC2 using **Gunicorn** as the WSGI server to run the Flask application.  
The app was started with the command:  

```bash
gunicorn app:app --bind 0.0.0.0:8000

