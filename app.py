from flask import Flask, request, send_file, render_template, jsonify
import os
import tempfile
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.service import Service as ChromeService
from selenium.webdriver.chrome.options import Options as ChromeOptions
import time
import random
from werkzeug.utils import secure_filename
from io import BytesIO
from flask_httpauth import HTTPBasicAuth
from openpyxl import Workbook
from datetime import datetime, timedelta
import uuid
from collections import OrderedDict
from threading import Thread
from queue import Queue
from pathlib import Path
from apscheduler.schedulers.background import BackgroundScheduler
import atexit

# Define base directory
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
PROGRESS_FILE = os.path.join(tempfile.gettempdir(), 'progress.txt')
UPLOAD_FOLDER = os.path.join(BASE_DIR, 'uploads')
RESULTS_FOLDER = os.path.join(BASE_DIR, 'results')

app = Flask(__name__, static_folder='static')
auth = HTTPBasicAuth()
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024
app.config['MAX_URLS'] = 1000

# Ensure upload folder exists
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
os.makedirs(RESULTS_FOLDER, exist_ok=True)

# Hardcoded credentials
USERS = {
    "raimonda": "2024Kainos00+"
}

@auth.verify_password
def verify_password(username, password):
    if username in USERS and USERS[username] == password:
        return username

def get_price_from_url(url, driver):
    try:
        driver.get(url)
        time.sleep(random.uniform(3, 7))  # Random delay between 3-7 seconds
        
        # First approach: Try to get all prices with class="price"
        try:
            wait = WebDriverWait(driver, 10)
            price_elements = wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, 'price'))
            )
            if price_elements:
                prices = []
                for element in price_elements:
                    price_text = element.text.strip()
                    # Only replace comma with period for float conversion
                    price_number = price_text.replace(',', '.').replace('€', '').strip()
                    try:
                        prices.append(float(price_number))
                    except ValueError:
                        continue
                
                if prices:
                    return min(prices)  # Return just the number for consistent handling
        except Exception as e:
            print(f"First approach failed: {str(e)}")
        
        # Second approach: Try to get all prices from price-container
        try:
            price_containers = wait.until(
                EC.presence_of_all_elements_located((By.CLASS_NAME, 'price-container'))
            )
            if price_containers:
                prices = []
                for container in price_containers:
                    price_text = container.text.strip()
                    # Only replace comma with period for float conversion
                    price_number = price_text.replace(',', '.').replace('€', '').strip()
                    try:
                        prices.append(float(price_number))
                    except ValueError:
                        continue
                
                if prices:
                    return min(prices)  # Return just the number for consistent handling
        except Exception as e:
            print(f"Second approach failed: {str(e)}")
            
    except Exception as e:
        print(f"Error processing URL {url}: {str(e)}")
    return None

def process_urls(urls, job):
    driver = None
    try:
        if len(urls) > app.config['MAX_URLS']:
            raise ValueError(f"Too many URLs. Maximum allowed is {app.config['MAX_URLS']}")

        options = ChromeOptions()
        options.add_argument('--headless')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--window-size=1920,1080')
        options.add_argument('--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36')
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        options.page_load_strategy = 'normal'
        
        service = ChromeService()
        driver = webdriver.Chrome(service=service, options=options)
        driver.set_page_load_timeout(30)
        driver.set_script_timeout(30)
        driver.implicitly_wait(10)
        
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        # Create Excel workbook
        wb = Workbook()
        ws = wb.active
        ws.append(['URL', 'Price'])  # Headers
        
        results = []
        total_urls = len(urls)
        
        for index, url in enumerate(urls, 1):
            url = url.strip()
            if url:
                try:
                    # Initial delay before first request
                    if index == 1:
                        time.sleep(random.uniform(1, 3))
                        
                    price = get_price_from_url(url, driver)
                    results.append([url, f"{price}€" if price is not None else "Not found"])
                except Exception as e:
                    print(f"Error processing URL {url}: {str(e)}")
                    results.append([url, "Error processing"])
                
                # Update job progress
                job.progress = index
                
                # Longer delay every 10 requests
                if index % 10 == 0:
                    time.sleep(random.uniform(5, 10))
        
        # Write results to Excel
        for row in results:
            ws.append(row)
        
        # Save to file instead of memory
        result_filename = f'prices_output_{job.id}.xlsx'
        result_path = os.path.join(RESULTS_FOLDER, result_filename)
        wb.save(result_path)
        job.result_path = result_path
        return result_path
        
    except Exception as e:
        print(f"Process URLs error: {str(e)}")
        raise e
    finally:
        if driver:
            driver.quit()

# Add near the top with other config
JOBS = OrderedDict()  # Store jobs in memory
job_queue = Queue()

class Job:
    def __init__(self, id, filename, total_urls):
        self.id = id
        self.filename = filename
        self.status = "pending"
        self.progress = 0
        self.total = total_urls
        self.result_path = None  # Add this to store file path
        self.error = None
        self.created_at = datetime.now()
        self.urls = []

def process_job_queue():
    while True:
        job = job_queue.get()
        try:
            job.status = "processing"
            job.progress = 0
            job.result_path = process_urls(job.urls, job)
            job.status = "completed"
        except Exception as e:
            print(f"Job processing error: {str(e)}")  # Add error logging
            job.status = "failed"
            job.error = str(e)
        finally:
            job_queue.task_done()

# Start worker thread
worker_thread = Thread(target=process_job_queue, daemon=True)
worker_thread.start()

@app.route('/')
@auth.login_required
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
@auth.login_required
def upload_file():
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file uploaded'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not file.filename.endswith('.txt'):
            return jsonify({'error': 'Please upload a .txt file'}), 400
        
        urls = file.read().decode('utf-8').splitlines()
        
        if len(urls) > app.config['MAX_URLS']:
            return jsonify({'error': f'Too many URLs. Maximum allowed is {app.config["MAX_URLS"]}'}), 400
        
        # Create new job
        job_id = str(uuid.uuid4())
        job = Job(job_id, file.filename, len(urls))
        job.urls = urls  # Store URLs for processing
        
        # Add to jobs dict and queue
        JOBS[job_id] = job
        job_queue.put(job)
        
        # Keep only last 10 jobs
        while len(JOBS) > 10:
            JOBS.popitem(last=False)
        
        return jsonify({
            'message': 'File uploaded successfully',
            'job_id': job_id
        })
        
    except Exception as e:
        print(f"Error in upload_file: {str(e)}")
        return jsonify({'error': str(e)}), 500

@app.route('/progress')
@auth.login_required
def get_progress():
    try:
        if not os.path.exists(PROGRESS_FILE):
            return jsonify({
                'current': 0,
                'total': 0,
                'percentage': 0
            })
            
        with open(PROGRESS_FILE, 'r') as f:
            progress = f.read().strip()
            if not progress:  # Handle empty file
                return jsonify({
                    'current': 0,
                    'total': 0,
                    'percentage': 0
                })
            try:
                current, total = map(int, progress.split('/'))
                return jsonify({
                    'current': current,
                    'total': total,
                    'percentage': round((current / total) * 100) if total > 0 else 0
                })
            except ValueError:  # Handle malformed content
                return jsonify({
                    'current': 0,
                    'total': 0,
                    'percentage': 0
                })
    except Exception as e:
        print(f"Error reading progress: {str(e)}")
        return jsonify({
            'current': 0,
            'total': 0,
            'percentage': 0
        })

@app.route('/cleanup', methods=['POST'])
@auth.login_required
def cleanup():
    if os.path.exists(PROGRESS_FILE):
        os.remove(PROGRESS_FILE)
    return jsonify({'status': 'success'})

@app.route('/jobs', methods=['GET'])
@auth.login_required
def get_jobs():
    return jsonify([{
        'id': job.id,
        'filename': job.filename,
        'status': job.status,
        'progress': job.progress,
        'total': job.total,
        'created_at': job.created_at.isoformat()
    } for job in JOBS.values()])

@app.route('/jobs/<job_id>/download', methods=['GET'])
@auth.login_required
def download_job(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    if job.status != 'completed':
        return jsonify({'error': 'Job not completed'}), 400
    
    if not job.result_path or not os.path.exists(job.result_path):
        return jsonify({'error': 'Result file not found'}), 404
    
    return send_file(
        job.result_path,
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        as_attachment=True,
        download_name=f'prices_output_{job_id}.xlsx'
    )

@app.route('/jobs/<job_id>/status', methods=['GET'])
@auth.login_required
def get_job_status(job_id):
    if job_id not in JOBS:
        return jsonify({'error': 'Job not found'}), 404
    
    job = JOBS[job_id]
    return jsonify({
        'id': job.id,
        'status': job.status,
        'progress': job.progress,
        'total': job.total,
        'error': job.error,
        'created_at': job.created_at.isoformat()
    })

@app.route('/debug/jobs', methods=['GET'])
@auth.login_required
def debug_jobs():
    return jsonify({
        'active_jobs': len(JOBS),
        'queue_size': job_queue.qsize(),
        'jobs': [{
            'id': job.id,
            'status': job.status,
            'progress': job.progress,
            'total': job.total,
            'error': job.error,
            'created_at': job.created_at.isoformat()
        } for job in JOBS.values()]
    })

# Add cleanup function to remove old files
def cleanup_old_files():
    try:
        # Keep files from last 24 hours
        cutoff = datetime.now() - timedelta(hours=24)
        
        for job in list(JOBS.values()):
            if job.created_at < cutoff:
                if job.result_path and os.path.exists(job.result_path):
                    os.remove(job.result_path)
                JOBS.pop(job.id, None)
                
    except Exception as e:
        print(f"Cleanup error: {str(e)}")

scheduler = BackgroundScheduler()
scheduler.add_job(func=cleanup_old_files, trigger="interval", hours=1)
scheduler.start()

# Shut down the scheduler when exiting the app
atexit.register(lambda: scheduler.shutdown())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)