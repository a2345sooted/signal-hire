import { Component, OnInit, inject, ChangeDetectorRef, Inject } from '@angular/core';
import { Title } from '@angular/platform-browser';
import { RouterOutlet, RouterModule, Router, NavigationEnd } from '@angular/router';
import { CommonModule } from '@angular/common';
import { MatToolbarModule } from '@angular/material/toolbar';
import { MatButtonModule } from '@angular/material/button';
import { MatCardModule } from '@angular/material/card';
import { MatListModule } from '@angular/material/list';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialogModule, MatDialog, MAT_DIALOG_DATA, MatDialogRef } from '@angular/material/dialog';
import { MatExpansionModule } from '@angular/material/expansion';
import { BreakpointObserver, Breakpoints } from '@angular/cdk/layout';
import { JobService, Job } from './services/job.service';
import { filter, map, shareReplay } from 'rxjs/operators';
import { Observable } from 'rxjs';

import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';

@Component({
  selector: 'app-resume-confirm-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatIconModule],
  template: `
    <div style="padding: 24px; min-width: 320px;">
      <h2 mat-dialog-title>Confirm Upload</h2>
      <mat-dialog-content>
        <p>Are you sure you want to upload <strong>{{ data.filename }}</strong>?</p>
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button mat-dialog-close>Cancel</button>
        <button mat-raised-button color="primary" [mat-dialog-close]="true">Upload</button>
      </mat-dialog-actions>
    </div>
  `
})
export class ResumeConfirmDialogComponent {
  data = inject(MAT_DIALOG_DATA);
}

@Component({
  selector: 'app-job-details-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatDividerModule, MatExpansionModule, MatIconModule, MatCardModule, RouterModule, MatListModule],
  template: `
    <div class="dialog-header">
      <h2 mat-dialog-title>{{ data.job.job_title }}</h2>
      <button mat-icon-button (click)="close()">
        <mat-icon>close</mat-icon>
      </button>
    </div>
    <mat-dialog-content>
      <mat-accordion multi="true">
        <mat-expansion-panel [expanded]="false">
          <mat-expansion-panel-header>
            <mat-panel-title> Job Description </mat-panel-title>
          </mat-expansion-panel-header>
          <div class="panel-inner">
            <div style="margin-bottom: 16px;">
              <strong>Department:</strong> {{ data.job.department }}
            </div>
            <mat-divider style="margin-bottom: 16px;"></mat-divider>
            <div class="markdown-container" [innerHTML]="data.job.markdown_text"></div>
          </div>
        </mat-expansion-panel>

        <mat-expansion-panel [expanded]="false">
          <mat-expansion-panel-header>
            <mat-panel-title> Resumes </mat-panel-title>
          </mat-expansion-panel-header>

          <div class="panel-inner">
            <div style="margin-bottom: 16px; display: flex; justify-content: flex-end;">
              <button mat-stroked-button color="primary" class="upload-btn" (click)="uploadResume()">
                <mat-icon>upload</mat-icon> Upload Resume
              </button>
            </div>
            <div *ngIf="data.job.resumes && data.job.resumes.length > 0; else noResumes">
              <mat-selection-list [multiple]="false" class="resume-list">
                <mat-list-item *ngFor="let resume of data.job.resumes"
                          [routerLink]="resume.analysis_id ? ['/analysis', resume.analysis_id] : ['/resume', resume.id, 'analysis']"
                          (click)="close()">
                  <span matListItemTitle>{{ resume.original_filename }}</span>
                  <span matListItemLine *ngIf="resume.structured_data?.rank">
                    Rank: {{ resume.structured_data.rank }}
                  </span>
                  <mat-icon matListItemMeta>chevron_right</mat-icon>
                </mat-list-item>
              </mat-selection-list>
            </div>
            <ng-template #noResumes>
              <p class="empty-msg">No resumes uploaded yet.</p>
            </ng-template>
          </div>
        </mat-expansion-panel>
      </mat-accordion>
    </mat-dialog-content>
  `,
  styles: [`
    .dialog-header {
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 16px;
      background: white;
      position: sticky;
      top: 0;
      z-index: 10;
      border-bottom: 1px solid #d2d2d7;
    }
    h2[mat-dialog-title] {
      margin: 0 !important;
      padding: 0 !important;
    }
    mat-dialog-content {
      padding: 0 !important;
      margin: 0 !important;
      max-height: none !important;
    }
    .panel-inner {
      padding: 16px 0;
    }
    .markdown-container {
      line-height: 1.6;
      font-size: 1rem;
      white-space: pre-wrap;
    }
    .resume-list {
      display: flex;
      flex-direction: column;
    }
    .empty-msg {
      color: #86868b;
      font-style: italic;
      padding: 16px 0;
    }
    :host ::ng-deep .hl-green { background: #e8f5e9; color: #2e7d32; padding: 0 4px; border-radius: 4px; font-weight: 600; }
    :host ::ng-deep .hl-yellow { background: #fffde7; color: #f57f17; padding: 0 4px; border-radius: 4px; font-weight: 600; }
    :host ::ng-deep .hl-blue { background: #e3f2fd; color: #1565c0; padding: 0 4px; border-radius: 4px; font-weight: 600; }
  `]
})
export class JobDetailsDialogComponent {
  private jobService = inject(JobService);
  private dialog = inject(MatDialog);
  private router = inject(Router);

  constructor(
    @Inject(MAT_DIALOG_DATA) public data: { job: Job },
    private dialogRef: MatDialogRef<JobDetailsDialogComponent>
  ) {}

  uploadResume() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.docx';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (file && this.data.job) {
        const jobId = this.data.job.id;

        const confirmRef = this.dialog.open(ResumeConfirmDialogComponent, {
          data: { filename: file.name }
        });

        confirmRef.afterClosed().subscribe(confirmed => {
          if (confirmed) {
            this.jobService.uploadResume(jobId, file).subscribe({
              next: (res) => {
                console.log('Resume uploaded successfully', res);
                this.close(); // Close job details dialog
                this.router.navigate(['/resume/upload', jobId], { queryParams: { resumeId: res.resume_id } });
              },
              error: (err) => {
                console.error('Error uploading resume', err);
              }
            });
          }
        });
      }
    };
    input.click();
  }

  close() {
    this.dialogRef.close();
  }
}

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [
    CommonModule,
    RouterOutlet,
    RouterModule,
    MatToolbarModule,
    MatButtonModule,
    MatCardModule,
    MatListModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatDialogModule,
    MatExpansionModule
  ],
  templateUrl: './app.html',
  styleUrl: './app.scss'
})
export class App implements OnInit {
  title = 'Signal Hire';
  private jobService = inject(JobService);
  private router = inject(Router);
  private titleService = inject(Title);
  private dialog = inject(MatDialog);
  private cdr = inject(ChangeDetectorRef);
  private breakpointObserver = inject(BreakpointObserver);

  isHandset$: Observable<boolean> = this.breakpointObserver.observe(Breakpoints.Handset)
    .pipe(
      map(result => result.matches),
      shareReplay()
    );

  jobs: Job[] = [];
  selectedJob: Job | null = null;
  isHandset = false;

  ngOnInit() {
    this.titleService.setTitle('Signal Hire');
    this.loadJobs();

    this.isHandset$.subscribe(isHandset => {
      this.isHandset = isHandset;
      if (!isHandset) {
        this.dialog.closeAll();
      }
    });

    // Refresh jobs when navigating back to root
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe((event: any) => {
      const url = event.urlAfterRedirects || event.url;
      const path = url.split('?')[0];
      if (path === '/' || path === '/#' || path === '') {
        this.loadJobs();

        // Check for jobId in query params to auto-select
        const urlParams = new URLSearchParams(window.location.search);
        const jobId = urlParams.get('jobId');
        if (jobId) {
          // We'll wait a bit for jobs to load
          setTimeout(() => {
            const job = this.jobs.find(j => j.id === jobId);
            if (job) {
              this.selectJob(job);
            }
          }, 500);
        }
      }
    });
  }

  loadJobs() {
    this.jobService.getJobs().subscribe({
      next: (jobs) => {
        this.jobs = jobs || [];
        // If we already have a selectedJob, try to find it in the new list to update it
        if (this.selectedJob) {
          const found = this.jobs.find(j => j.id === this.selectedJob?.id);
          if (found) {
            this.selectedJob = found;
          } else if (this.jobs.length > 0) {
            this.selectedJob = this.jobs[0];
          } else {
            this.selectedJob = null;
          }
        } else if (this.jobs.length > 0) {
          this.selectedJob = this.jobs[0];
        }
        this.cdr.detectChanges();
      },
      error: (err) => {
        console.error('Error loading jobs:', err);
      }
    });
  }

  selectJob(job: Job) {
    this.selectedJob = job;
    if (this.isHandset) {
      this.dialog.open(JobDetailsDialogComponent, {
        data: { job },
        width: '100vw',
        maxWidth: '100vw',
        height: '100vh',
        maxHeight: '100vh',
        panelClass: 'full-screen-dialog'
      });
    }
  }

  viewFullJd(job: Job, event: MouseEvent) {
    event.stopPropagation();
    this.dialog.open(JobDetailsDialogComponent, {
      data: { job },
      width: '800px',
      maxWidth: '90vw'
    });
  }

  isRouteActive(): boolean {
    const url = this.router.url.split('?')[0];
    return url !== '/' && url !== '/#';
  }

  uploadResume() {
    // Trigger file input
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.pdf,.docx';
    input.onchange = (e: any) => {
      const file = e.target.files[0];
      if (file && this.selectedJob) {
        const jobId = this.selectedJob.id;

        const confirmRef = this.dialog.open(ResumeConfirmDialogComponent, {
          data: { filename: file.name }
        });

        confirmRef.afterClosed().subscribe(confirmed => {
          if (confirmed) {
            this.jobService.uploadResume(jobId, file).subscribe({
              next: (res) => {
                console.log('Resume uploaded successfully', res);
                this.router.navigate(['/resume/upload', jobId], { queryParams: { resumeId: res.resume_id } });
              },
              error: (err) => {
                console.error('Error uploading resume', err);
              }
            });
          }
        });
      }
    };
    input.click();
  }
}
