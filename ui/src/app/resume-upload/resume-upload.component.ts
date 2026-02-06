import { Component, OnInit, OnDestroy, inject, ChangeDetectorRef } from '@angular/core';
import { CommonModule, Location } from '@angular/common';
import { MatCardModule } from '@angular/material/card';
import { MatProgressBarModule } from '@angular/material/progress-bar';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { ActivatedRoute, Router } from '@angular/router';
import { LoggerService } from '../services/logger.service';
import { JobService } from '../services/job.service';

@Component({
  selector: 'app-resume-upload',
  standalone: true,
  imports: [
    CommonModule,
    MatProgressBarModule,
    MatButtonModule,
    MatIconModule
  ],
  template: `
    <div class="upload-container">
      <div class="status-content">
        <h2 class="status-title">{{ statusText }}</h2>

        <p *ngIf="statusMessage" class="detail-msg">{{ statusMessage }}</p>

        <div *ngIf="processing" class="progress-container">
          <mat-progress-bar mode="indeterminate"></mat-progress-bar>
          <div class="actions">
             <button mat-button color="warn" (click)="stopProcessing()" [disabled]="stopping">
               <mat-icon>stop</mat-icon> Stop
             </button>
          </div>
        </div>

        <div *ngIf="completed" class="result-icon success">
          <mat-icon>check_circle</mat-icon>
          <p>Analysis complete! Redirecting...</p>
        </div>

        <div *ngIf="failed" class="result-icon error">
          <mat-icon>error</mat-icon>
          <p>{{ errorMessage || 'Processing failed' }}</p>
          <div class="actions">
            <button mat-button (click)="goBack()">Back to Home</button>
            <button mat-raised-button color="primary" (click)="retry()">Retry</button>
          </div>
        </div>
      </div>
    </div>
  `,
  styles: [`
    .upload-container {
      display: flex;
      justify-content: center;
      align-items: center;
      min-height: calc(100vh - 120px);
      padding: 24px;
    }
    .status-content {
      width: 100%;
      max-width: 500px;
      display: flex;
      flex-direction: column;
      align-items: center;
      text-align: center;
    }
    .status-title {
      margin-bottom: 8px;
      font-size: 1.5rem;
      font-weight: 500;
    }
    .progress-container {
      width: 100%;
      margin-top: 24px;
      margin-bottom: 24px;
    }
    .wait-msg {
      margin-top: 16px;
      color: #666;
      font-size: 1rem;
    }
    .detail-msg {
      margin-bottom: 16px;
      font-style: italic;
      color: #888;
      font-size: 0.9rem;
    }
    .result-icon {
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 16px;
    }
    .result-icon mat-icon {
      font-size: 80px;
      width: 80px;
      height: 80px;
    }
    .success mat-icon { color: #4caf50; }
    .error mat-icon { color: #f44336; }
    .actions {
      margin-top: 24px;
      display: flex;
      gap: 12px;
    }
  `]
})
export class ResumeUploadComponent implements OnInit, OnDestroy {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private logger = inject(LoggerService);
  private jobService = inject(JobService);
  private cdr = inject(ChangeDetectorRef);
  private location = inject(Location);

  jobId: string | null = null;
  resumeId: string | null = null;
  processing = true;
  completed = false;
  failed = false;
  stopping = false;
  statusText = 'Processing Resume';
  statusMessage = '';
  errorMessage = '';
  private socket?: WebSocket;

  ngOnInit() {
    this.jobId = this.route.snapshot.paramMap.get('jobId');
    this.resumeId = this.route.snapshot.queryParamMap.get('resumeId');

    if (this.jobId) {
      this.connectWebSocket(this.jobId);
    } else {
      this.statusText = 'Error';
      this.statusMessage = 'No Job ID provided';
      this.processing = false;
      this.failed = true;
    }
  }

  ngOnDestroy() {
    if (this.socket) {
      this.socket.close();
    }
  }

  connectWebSocket(jobId: string) {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = window.location.host;
    const socketUrl = `${protocol}//${host}/api/v1/ws/job/${jobId}`;

    this.socket = new WebSocket(socketUrl);

    this.socket.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.logger.log('Received WebSocket message', data);
        if (data.status) {
          this.statusText = data.status;
        }
        if (data.message) {
          this.statusMessage = data.message;
        }

        // If we have a resumeId from query params, filter for it
        const isMatch = !this.resumeId || data.resume_id === this.resumeId;

        if (data.completed && isMatch) {
          this.processing = false;
          this.completed = true;
          this.statusText = 'Completed';

          // Use the resume_id from the message if we didn't have one
          const targetResumeId = data.resume_id || this.resumeId;

          setTimeout(() => {
            this.router.navigate(['/resume', targetResumeId, 'analysis']);
            this.cdr.detectChanges();
          }, 1500);
        } else if (data.failed && isMatch) {
          this.processing = false;
          this.failed = true;
          this.statusText = 'Failed';
          this.errorMessage = data.message;
        } else if (data.stopped && isMatch) {
          this.processing = false;
          this.statusText = 'Stopped';
          this.statusMessage = data.message || 'Processing was stopped';

          // Navigate to job listings after a short delay so the user sees the "Stopped" status
          setTimeout(() => {
            this.router.navigate(['/']);
          }, 1000);
        }

        this.cdr.detectChanges();
      } catch (e) {
        this.logger.error('Error parsing WS message', e);
      }
    };

    this.socket.onerror = (error) => {
      this.logger.error('WebSocket error', error);
      this.processing = false;
      this.failed = true;
      this.statusText = 'Connection Error';
      this.errorMessage = 'Failed to connect to status updates.';
    };
  }

  goBack() {
    this.router.navigate(['/']);
  }

  retry() {
    // This would ideally trigger a retry on the backend
    window.location.reload();
  }

  stopProcessing() {
    if (!this.jobId || this.stopping) return;

    this.stopping = true;
    this.statusMessage = 'Stopping processing...';
    this.cdr.detectChanges();

    this.jobService.stopResumeProcessing(this.jobId).subscribe({
      next: (response) => {
        this.logger.log('Stop request successful', response);
        // Navigate to home page immediately upon successful stop request
        this.router.navigate(['/']);
      },
      error: (err) => {
        this.logger.error('Failed to stop processing', err);
        this.stopping = false;
        this.statusMessage = 'Failed to stop processing. Please try again.';
        this.cdr.detectChanges();
      }
    });
  }
}
