import { Component, OnInit, inject, ViewChild, TemplateRef, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { DomSanitizer, SafeHtml } from '@angular/platform-browser';
import { MatCardModule } from '@angular/material/card';
import { MatButtonModule } from '@angular/material/button';
import { MatIconModule } from '@angular/material/icon';
import { MatChipsModule } from '@angular/material/chips';
import { MatDividerModule } from '@angular/material/divider';
import { MatDialogModule, MatDialog } from '@angular/material/dialog';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { ActivatedRoute, RouterModule, Router } from '@angular/router';
import { JobService } from '../services/job.service';
import { forkJoin } from 'rxjs';

@Component({
  selector: 'app-resume-analysis',
  standalone: true,
  imports: [
    CommonModule,
    MatCardModule,
    MatButtonModule,
    MatIconModule,
    MatChipsModule,
    MatDividerModule,
    MatDialogModule,
    MatProgressSpinnerModule,
    RouterModule
  ],
  template: `
    <div class="results-container" *ngIf="!loading; else loadingState">
      <!-- Left Column: Navigation & Candidate Info -->
      <div class="sidebar">
        <div class="candidate-info">
          <h1 class="candidate-name">{{ resumeData?.structured_data?.contact?.name || 'Candidate' }}</h1>
          <p class="candidate-meta">
            <mat-icon inline>email</mat-icon> {{ resumeData?.structured_data?.contact?.email || 'No email' }}
          </p>
          <p class="candidate-meta" *ngIf="resumeData?.created_at">
            <mat-icon inline>calendar_today</mat-icon> Extracted: {{ resumeData.created_at | date:'mediumDate' }}
          </p>
        </div>

        <nav class="nav-buttons">
          <button mat-button [class.active]="currentView === 'analysis'" (click)="currentView = 'analysis'">
            <mat-icon>analytics</mat-icon> Show Analysis
          </button>
          <button mat-button [class.active]="currentView === 'jd'" (click)="currentView = 'jd'">
            <mat-icon>description</mat-icon> Show JD
          </button>
          <button mat-button [class.active]="currentView === 'resume' || currentView === 'resume_text'" (click)="currentView = 'resume'">
            <mat-icon>picture_as_pdf</mat-icon> Show Resume
          </button>
          <div class="sub-nav" *ngIf="currentView === 'resume' || currentView === 'resume_text'">
            <button mat-button class="sub-btn" [class.active]="currentView === 'resume'" (click)="currentView = 'resume'">
              <mat-icon>picture_as_pdf</mat-icon> PDF View
            </button>
            <button mat-button class="sub-btn" [class.active]="currentView === 'resume_text'" (click)="currentView = 'resume_text'">
              <mat-icon>text_format</mat-icon> Raw Text
            </button>
          </div>
          <mat-divider></mat-divider>
          <button mat-button (click)="goBack()" class="back-home">
            <mat-icon>home</mat-icon> Back to Home
          </button>
        </nav>
      </div>

      <!-- Right Column: Content Area -->
      <div class="main-content">
        <div *ngIf="currentView === 'analysis'" class="analysis-view">
          <div class="analysis-header">
            <div class="score-container">
              <div class="score-dial">
                <svg viewBox="0 0 100 100">
                  <path class="bg" d="M 10 50 A 40 40 0 1 1 90 50" />
                  <path class="meter" d="M 10 50 A 40 40 0 1 1 90 50" stroke-dasharray="125.6" [attr.stroke-dashoffset]="125.6 * (1 - (analysisData?.content?.score || 0) / 100)" />
                </svg>
                <div class="score-value">{{ analysisData?.content?.score || 0 }}</div>
                <div class="score-label">Match Score</div>
              </div>
            </div>
            <div class="impression-section">
              <h3 class="section-title">Overall Impression</h3>
              <div class="impression-text" [innerHTML]="summaryHtml">
              </div>
            </div>
          </div>

          <div class="analysis-grid">
            <section class="analysis-section">
              <h3 class="section-title strengths"><mat-icon inline>check_circle</mat-icon> Strengths</h3>
              <ul class="bullet-list">
                <li *ngFor="let s of (analysisData?.content?.major_hits || [])">{{ s }}</li>
                <li *ngFor="let s of (analysisData?.content?.minor_hits || [])">{{ s }}</li>
              </ul>
              <p *ngIf="!(analysisData?.content?.major_hits?.length || analysisData?.content?.minor_hits?.length)">No strengths identified.</p>
            </section>

            <section class="analysis-section">
              <h3 class="section-title major-gaps"><mat-icon inline>error</mat-icon> Major Gaps</h3>
              <ul class="bullet-list">
                <li *ngFor="let g of (analysisData?.content?.major_gaps || [])">{{ g }}</li>
              </ul>
              <p *ngIf="!analysisData?.content?.major_gaps?.length">No major gaps identified.</p>
            </section>

            <section class="analysis-section">
              <h3 class="section-title minor-gaps"><mat-icon inline>warning</mat-icon> Minor Gaps</h3>
              <ul class="bullet-list">
                <li *ngFor="let g of (analysisData?.content?.minor_gaps || [])">{{ g }}</li>
              </ul>
              <p *ngIf="!analysisData?.content?.minor_gaps?.length">No minor gaps identified.</p>
            </section>

            <!-- <section class="analysis-section">
              <h3 class="section-title roles"><mat-icon inline>assignment_ind</mat-icon> Other Possible Roles</h3>
              <div class="chips-container">
                <mat-chip-row *ngFor="let role of roles" (click)="openRoleModal(role)" class="clickable-chip">
                  {{ role.title }} - {{ role.department }}
                </mat-chip-row>
              </div>
            </section> -->
          </div>
        </div>

        <div *ngIf="currentView === 'jd'" class="jd-view">
          <div class="jd-header">
            <h2>{{ jobData?.title || 'Job Description' }}</h2>
            <p class="department-tag">{{ jobData?.department }}</p>
          </div>
          <mat-divider></mat-divider>
          <div class="jd-content">
             <div class="markdown-container" [innerHTML]="jdHtml"></div>
          </div>
        </div>

        <div *ngIf="currentView === 'resume'" class="resume-view">
          <div class="resume-pdf-container" *ngIf="resumePdfUrl">
            <iframe [src]="resumePdfUrl" width="100%" height="100%" frameborder="0"></iframe>
          </div>
        </div>

        <div *ngIf="currentView === 'resume_text'" class="resume-view">
          <div class="resume-content">
            <pre style="white-space: pre-wrap; font-family: inherit;">{{ resumeData?.raw_text || (resumeData?.structured_data | json) }}</pre>
          </div>
        </div>
      </div>
    </div>

    <ng-template #loadingState>
      <div class="loading-container">
        <mat-spinner diameter="50"></mat-spinner>
        <p>Loading analysis ({{loading}})...</p>
      </div>
    </ng-template>

    <!-- Role Modal Template -->
    <ng-template #roleModal let-data>
      <h2 mat-dialog-title>{{ data.title }}</h2>
      <mat-dialog-content>
        <p><strong>Department:</strong> {{ data.department }}</p>
        <p>Would you like to analyze this candidate specifically for this role?</p>
      </mat-dialog-content>
      <mat-dialog-actions align="end">
        <button mat-button mat-dialog-close>Close</button>
        <button mat-raised-button color="primary" (click)="analyzeForRole(data)">Analyze</button>
      </mat-dialog-actions>
    </ng-template>
  `,
  styles: [`
    .results-container {
      display: flex;
      min-height: calc(100vh - 64px);
      max-width: 1400px;
      margin: 0 auto;
    }

    .sidebar {
      width: 300px;
      background: #f8f9fa;
      border-right: 1px solid #e0e0e0;
      padding: 32px 24px;
      display: flex;
      flex-direction: column;
      gap: 40px;
    }

    .candidate-name {
      font-size: 1.5rem;
      font-weight: 700;
      margin-bottom: 8px;
      color: #1a1a1a;
    }

    .candidate-meta {
      font-size: 0.9rem;
      color: #666;
      display: flex;
      align-items: center;
      gap: 4px;
    }

    .nav-buttons {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }

    .nav-buttons button {
      justify-content: flex-start;
      padding: 12px 16px;
      border-radius: 8px;
      font-weight: 500;
      color: #444;
    }

    .nav-buttons button mat-icon { margin-right: 12px; }
    .nav-buttons button.active {
      background: #e3f2fd;
      color: #1976d2;
    }

    .sub-nav {
      display: flex;
      flex-direction: column;
      margin-left: 24px;
      margin-top: -4px;
      margin-bottom: 8px;
    }

    .sub-btn {
      font-size: 0.85rem !important;
      height: 36px !important;
      color: #666 !important;
    }

    .sub-btn.active {
      color: #1976d2 !important;
      font-weight: 600 !important;
    }

    .main-content {
      flex: 1;
      padding: 40px;
      background: white;
    }

    .analysis-header {
      display: flex;
      align-items: center;
      gap: 48px;
      margin-bottom: 48px;
      padding-bottom: 48px;
      border-bottom: 1px solid #f0f0f0;
    }

    .score-dial {
      position: relative;
      width: 120px;
      height: 120px;
      text-align: center;
    }

    .score-dial svg {
      width: 100%;
      height: 100%;
      transform: rotate(-90deg);
    }

    .score-dial path {
      fill: none;
      stroke-width: 8;
      stroke-linecap: round;
    }

    .score-dial path.bg { stroke: #eee; }
    .score-dial path.meter {
      stroke: #4caf50;
      transition: stroke-dashoffset 1s ease-out;
    }

    .score-value {
      position: absolute;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      font-size: 2rem;
      font-weight: 700;
      color: #333;
    }

    .score-label {
      font-size: 0.75rem;
      color: #888;
      margin-top: 4px;
      text-transform: uppercase;
      letter-spacing: 0.05em;
    }

    .impression-section { flex: 1; }
    .section-title {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 16px;
      display: flex;
      align-items: center;
      gap: 8px;
      color: #333;
    }

    .impression-text {
      line-height: 1.6;
      color: #555;
      font-size: 1.05rem;
    }

    .analysis-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 40px;
    }

    .analysis-section {
      background: #fafafa;
      padding: 24px;
      border-radius: 12px;
      border: 1px solid #f0f0f0;
    }

    .bullet-list {
      margin: 0;
      padding-left: 20px;
      color: #555;
    }

    .bullet-list li { margin-bottom: 8px; }

    .section-title.strengths mat-icon { color: #4caf50; }
    .section-title.minor-gaps mat-icon { color: #ff9800; }
    .section-title.major-gaps mat-icon { color: #f44336; }
    .section-title.roles mat-icon { color: #2196f3; }

    .chips-container { display: flex; flex-wrap: wrap; gap: 8px; }

    .clickable-chip {
      cursor: pointer;
      transition: transform 0.2s;
    }

    .clickable-chip:hover {
      transform: scale(1.05);
      filter: brightness(0.95);
    }

    .placeholder-view {
      padding: 40px;
      text-align: center;
      color: #666;
    }

    @media (max-width: 900px) {
      .results-container { flex-direction: column; }
      .sidebar { width: 100%; border-right: none; border-bottom: 1px solid #e0e0e0; }
      .analysis-header { flex-direction: column; text-align: center; gap: 24px; }
      .main-content { padding: 24px; }
    }

    .loading-container {
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      height: 100%;
      min-height: 400px;
      gap: 16px;
    }

    .jd-header {
      margin-bottom: 24px;
    }

    .department-tag {
      color: #666;
      font-weight: 500;
      text-transform: uppercase;
      font-size: 0.8rem;
    }

    .jd-content {
      margin-top: 24px;
      line-height: 1.6;
      color: #333;
    }

    .resume-content {
      line-height: 1.6;
      color: #333;
    }

    .resume-pdf-container {
      height: calc(100vh - 120px);
      border: 1px solid #e0e0e0;
      border-radius: 8px;
      overflow: hidden;
      background: #525659;
    }

    .markdown-container {
      line-height: 1.6;
      font-size: 1rem;
    }

    :host ::ng-deep .hl-green { background: #e8f5e9; color: #2e7d32; padding: 0 4px; border-radius: 4px; font-weight: 600; }
    :host ::ng-deep .hl-yellow { background: #fffde7; color: #f57f17; padding: 0 4px; border-radius: 4px; font-weight: 600; }
    :host ::ng-deep .hl-blue { background: #e3f2fd; color: #1565c0; padding: 0 4px; border-radius: 4px; font-weight: 600; }
  `]
})
export class ResumeAnalysisComponent implements OnInit {
  @ViewChild('roleModal') roleModalTemplate!: TemplateRef<any>;

  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private dialog = inject(MatDialog);
  private jobService = inject(JobService);
  private sanitizer = inject(DomSanitizer);
  private cdr = inject(ChangeDetectorRef);

  currentView: 'analysis' | 'jd' | 'resume' | 'resume_text' = 'analysis';
  resumeId: string | null = null;
  analysisId: string | null = null;
  jobId: string | null = null;

  loading = true;
  resumeData: any;
  jobData: any;
  analysisData: any;
  summaryHtml: SafeHtml | string = '';
  jdHtml: SafeHtml | string = '';
  resumePdfUrl: SafeHtml | null = null;

  get roles() {
    return [
      { title: 'Senior Full Stack Engineer', department: 'Engineering' },
      { title: 'Technical Lead', department: 'Engineering' },
      { title: 'Cloud Architect', department: 'Infrastructure' }
    ];
  }

  ngOnInit() {
    console.log('ResumeAnalysisComponent.ngOnInit');
    const path = this.route.snapshot.url.map(segment => segment.path).join('/');
    const id = this.route.snapshot.paramMap.get('id');

    // Also try to get jobId from query params
    this.jobId = this.route.snapshot.queryParamMap.get('jobId');
    console.log('Detected jobId from query params:', this.jobId);

    if (path.includes('analysis/')) {
        // This is /analysis/:id
        this.analysisId = id;
    } else {
        // This is /resume/:id/analysis
        this.resumeId = id;
    }

    if (this.analysisId) {
      this.loadAnalysis();
    } else if (this.resumeId) {
      this.loadAnalysis();
    } else {
      console.error('Missing ID');
      this.loading = false;
    }
  }

  loadAnalysis() {
    this.loading = true;
    if (this.analysisId) {
      console.log('Loading analysis by ID:', this.analysisId);
      this.jobService.getAnalysisById(this.analysisId).subscribe({
        next: (res) => {
          console.log('Received analysis data:', res);
          // res contains {analysis, resume_id, resume_name, resume_email, resume_structured_data, job_title, job_markdown}
          this.analysisData = { content: res.analysis };
          this.resumeId = res.resume_id;

          this.resumeData = {
            structured_data: res.resume_structured_data || {
              contact: {
                name: res.resume_name,
                email: res.resume_email
              }
            }
          };

          this.jobData = {
            markdown_content: res.job_markdown,
            title: res.job_title
          };

          this.processAnalysisData();
          this.loading = false;
          console.log('Setting loading to false, final state:', {
            loading: this.loading,
            analysisData: !!this.analysisData,
            resumeData: !!this.resumeData
          });
          this.cdr.detectChanges();
        },
        error: (err) => {
          console.error('Error loading analysis by ID:', err);
          this.loading = false;
          this.cdr.detectChanges();
        }
      });
    } else if (this.resumeId) {
      console.log('Loading analysis for resume:', this.resumeId);
      this.jobService.getResume(this.resumeId).subscribe({
        next: (resume) => {
          console.log('Received resume data:', resume);
          this.resumeData = resume;
          this.jobId = resume.job_id;

          if (this.jobId) {
            forkJoin({
              job: this.jobService.getJob(this.jobId),
              analysis: this.jobService.getAnalysis(this.resumeId!)
            }).subscribe({
              next: (results) => {
                console.log('Received forkJoin results:', results);
                this.jobData = results.job;
                this.analysisData = results.analysis;
                this.processAnalysisData();
                this.loading = false;
                this.cdr.detectChanges();
              },
              error: (err) => {
                console.error('Error loading job or analysis data:', err);
                this.loading = false;
                this.cdr.detectChanges();
              }
            });
          } else {
            console.error('No jobId associated with resume');
            this.loading = false;
            this.cdr.detectChanges();
          }
        },
        error: (err) => {
          console.error('Error loading resume data:', err);
          this.loading = false;
          this.cdr.detectChanges();
        }
      });
    }
  }

  private parseMarkdown(text: string): string {
    if (!text) return '';

    let html = text
      // Headers
      .replace(/^#### (.*$)/gm, '<h4>$1</h4>')
      .replace(/^### (.*$)/gm, '<h3>$1</h3>')
      .replace(/^## (.*$)/gm, '<h2>$1</h2>')
      .replace(/^# (.*$)/gm, '<h1>$1</h1>')
      // Bold
      .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
      .replace(/__(.*?)__/g, '<strong>$1</strong>')
      // Italic
      .replace(/\*(.*?)\*/g, '<em>$1</em>')
      .replace(/_(.*?)_/g, '<em>$1</em>')
      // Lists
      .replace(/^\s*-\s+(.*$)/gm, '<li>$1</li>')
      .replace(/^\s*\*\s+(.*$)/gm, '<li>$1</li>');

    // Wrap <li> groups in <ul>
    html = html.replace(/((?:<li>.*?<\/li>\n?)+)/g, (match) => `<ul>${match.trim()}</ul>\n`);

    // Handle <mark> tags (used in JD processor)
    html = html.replace(/<mark class="(.*?)">(.*?)<\/mark>/g, '<mark class="$1">$2</mark>');

    // Paragraphs and line breaks
    const blocks = html.split(/\n\n+/);
    html = blocks.map(block => {
      const trimmed = block.trim();
      if (!trimmed) return '';
      if (trimmed.startsWith('<h') || trimmed.startsWith('<ul') || trimmed.startsWith('<mark')) {
        return trimmed;
      }
      return `<p>${trimmed.replace(/\n/g, '<br>')}</p>`;
    }).join('\n');

    return html;
  }

  processAnalysisData() {
    console.log('Processing analysis data:', this.analysisData);

    // Set resume PDF URL
    const rid = this.resumeId || this.analysisData?.resume_id;
    if (rid) {
      const url = this.jobService.getResumePdfUrl(rid);
      this.resumePdfUrl = this.sanitizer.bypassSecurityTrustResourceUrl(url);
    }

    // Extract the summary from messages (last message is usually the summary)
    const messages = this.analysisData?.content?.messages || [];
    let rawSummary = '';
    if (messages.length > 0) {
      rawSummary = messages[messages.length - 1];
    } else {
      // Fallback: check if scoring_reasoning or other fields can be used as summary
      rawSummary = this.analysisData?.content?.scoring_reasoning || 'No summary available.';
    }

    this.summaryHtml = this.sanitizer.bypassSecurityTrustHtml(this.parseMarkdown(rawSummary));

    const rawJd = this.jobData?.markdown_content || this.jobData?.raw_text || '';
    this.jdHtml = this.sanitizer.bypassSecurityTrustHtml(this.parseMarkdown(rawJd));

    console.log('Summary HTML:', this.summaryHtml);
  }

  openRoleModal(role: any) {
    this.dialog.open(this.roleModalTemplate, {
      data: role,
      width: '400px'
    });
  }

  analyzeForRole(role: any) {
    this.dialog.closeAll();
    console.log('Analyzing for role:', role);
    alert(`Starting analysis for ${role.title} in ${role.department}... (Stub)`);
  }

  goBack() {
    if (this.jobId) {
      this.router.navigate(['/'], { queryParams: { jobId: this.jobId } });
    } else {
      this.router.navigate(['/']);
    }
  }
}
