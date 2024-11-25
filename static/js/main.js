document.addEventListener("DOMContentLoaded", function () {
  const dropZone = document.getElementById("dropZone");
  const fileInput = document.getElementById("file");
  const fileInfo = document.getElementById("fileInfo");
  const submitBtn = document.getElementById("submitBtn");
  let progressInterval;
  let jobsUpdateInterval;

  // Prevent default drag behaviors
  ["dragenter", "dragover", "dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, preventDefaults, false);
    document.body.addEventListener(eventName, preventDefaults, false);
  });

  // Highlight drop zone when item is dragged over it
  ["dragenter", "dragover"].forEach((eventName) => {
    dropZone.addEventListener(eventName, highlight, false);
  });

  ["dragleave", "drop"].forEach((eventName) => {
    dropZone.addEventListener(eventName, unhighlight, false);
  });

  // Handle dropped files
  dropZone.addEventListener("drop", handleDrop, false);

  function preventDefaults(e) {
    e.preventDefault();
    e.stopPropagation();
  }

  function highlight(e) {
    dropZone.classList.add("highlight");
    dropZone.style.borderColor = "#2980b9";
    dropZone.style.backgroundColor = "#f7f9fc";
  }

  function unhighlight(e) {
    dropZone.classList.remove("highlight");
    dropZone.style.borderColor = "#3498db";
    dropZone.style.backgroundColor = "white";
  }

  function handleDrop(e) {
    const dt = e.dataTransfer;
    const files = dt.files;

    if (files.length) {
      fileInput.files = files;
      updateFileInfo(files[0]);
    }
  }

  // Handle click upload
  dropZone.addEventListener("click", () => {
    fileInput.click();
  });

  fileInput.addEventListener("change", (e) => {
    if (e.target.files.length) {
      updateFileInfo(e.target.files[0]);
    }
  });

  function updateFileInfo(file) {
    if (file.name.endsWith(".txt")) {
      fileInfo.textContent = `Selected file: ${file.name}`;
      submitBtn.disabled = false;
    } else {
      fileInfo.textContent = "Please select a .txt file";
      submitBtn.disabled = true;
    }
  }

  function updateProgress() {
    fetch("/progress", {
        timeout: 30000  // 30 second timeout
    })
        .then(response => {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(data => {
            const progressText = document.getElementById("progressText");
            const progressFill = document.getElementById("progressFill");
            
            if (data && typeof data.current !== 'undefined' && typeof data.total !== 'undefined') {
                progressText.textContent = `Processed: ${data.current}/${data.total} (${data.percentage}%)`;
                progressFill.style.width = data.percentage + "%";
            }
        })
        .catch(error => {
            console.error("Progress update error:", error);
        });
  }

  function formatDate(isoString) {
    const date = new Date(isoString);
    return date.toLocaleString('lt-LT', {
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
  }

  function updateJobs() {
    fetch('/jobs', {
        headers: {
            'Authorization': 'Basic ' + btoa('raimonda:2024Kainos00+')
        }
    })
    .then(response => response.json())
    .then(jobs => {
        const tbody = document.getElementById('jobsTableBody');
        tbody.innerHTML = '';
        
        jobs.forEach(job => {
            const row = document.createElement('tr');
            
            // Job ID
            const idCell = document.createElement('td');
            idCell.textContent = job.id.substring(0, 8);
            
            // Filename
            const fileCell = document.createElement('td');
            fileCell.textContent = job.filename;
            
            // Date
            const dateCell = document.createElement('td');
            dateCell.textContent = formatDate(job.created_at);
            
            // Status
            const statusCell = document.createElement('td');
            const statusSpan = document.createElement('span');
            statusSpan.textContent = job.status.charAt(0).toUpperCase() + job.status.slice(1);
            statusSpan.className = `job-status status-${job.status}`;
            statusCell.appendChild(statusSpan);
            
            // Progress
            const progressCell = document.createElement('td');
            const progressContainer = document.createElement('div');
            progressContainer.className = 'job-progress';
            const progressFill = document.createElement('div');
            progressFill.className = 'job-progress-fill';
            const progress = job.status === 'completed' ? 100 : 
                           job.status === 'failed' ? 0 : 
                           Math.round((job.progress / job.total) * 100) || 0;
            progressFill.style.width = `${progress}%`;
            progressContainer.appendChild(progressFill);
            progressCell.appendChild(progressContainer);
            
            // Action
            const actionCell = document.createElement('td');
            const downloadBtn = document.createElement('button');
            downloadBtn.className = 'download-btn';
            downloadBtn.innerHTML = '<i class="fas fa-download"></i> Download';
            downloadBtn.disabled = job.status !== 'completed';
            
            if (job.status === 'completed') {
                downloadBtn.onclick = () => downloadJob(job.id);
            }
            
            actionCell.appendChild(downloadBtn);
            
            // Add all cells to row
            row.appendChild(idCell);
            row.appendChild(fileCell);
            row.appendChild(dateCell);
            row.appendChild(statusCell);
            row.appendChild(progressCell);
            row.appendChild(actionCell);
            
            tbody.appendChild(row);
        });
    })
    .catch(console.error);
  }

  function downloadJob(jobId) {
    window.location.href = `/jobs/${jobId}/download`;
  }

  // Modify the existing upload form submission
  document.getElementById("uploadForm").onsubmit = function(e) {
    e.preventDefault();
    
    const errorDiv = document.getElementById("errorMessage");
    errorDiv.style.display = "none";
    
    const formData = new FormData(this);
    
    fetch("/upload", {
        method: "POST",
        body: formData,
        headers: {
            'Authorization': 'Basic ' + btoa('raimonda:2024Kainos00+')
        }
    })
    .then(response => {
        if (!response.ok) {
            return response.json().then(data => {
                throw new Error(data.error || "An error occurred");
            });
        }
        return response.json();
    })
    .then(data => {
        // Reset form
        document.getElementById('file').value = '';
        document.getElementById('fileInfo').textContent = 'No file selected';
        document.getElementById('submitBtn').disabled = true;
        
        // Start or reset jobs update interval
        if (!jobsUpdateInterval) {
            jobsUpdateInterval = setInterval(updateJobs, 2000);
        }
        updateJobs(); // Update immediately
        
        // Show success message
        const successDiv = document.createElement('div');
        successDiv.className = 'success-message';
        successDiv.textContent = 'File uploaded successfully and added to processing queue';
        errorDiv.parentNode.insertBefore(successDiv, errorDiv);
        setTimeout(() => successDiv.remove(), 5000);
    })
    .catch(error => {
        console.error("Error:", error);
        errorDiv.textContent = error.message;
        errorDiv.style.display = "block";
    });
    
    return false;
  };

  // Initial jobs load
  updateJobs();
  jobsUpdateInterval = setInterval(updateJobs, 2000);

  // Cleanup interval when leaving page
  window.addEventListener('beforeunload', () => {
    if (jobsUpdateInterval) {
        clearInterval(jobsUpdateInterval);
    }
  });
});
