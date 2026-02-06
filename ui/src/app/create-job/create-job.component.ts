import { Component, inject, ChangeDetectorRef } from '@angular/core';
import { CommonModule } from '@angular/common';
import { FormsModule } from '@angular/forms';
import { MatDialogModule, MatDialog, MatDialogRef, MAT_DIALOG_DATA } from '@angular/material/dialog';
import { MatButtonModule } from '@angular/material/button';
import { MatFormFieldModule } from '@angular/material/form-field';
import { MatSelectModule } from '@angular/material/select';
import { MatInputModule } from '@angular/material/input';
import { MatProgressSpinnerModule } from '@angular/material/progress-spinner';
import { MatIconModule } from '@angular/material/icon';
import { Router, RouterModule } from '@angular/router';
import { JobService } from '../services/job.service';
import { LoggerService } from '../services/logger.service';
import { Inject } from '@angular/core';

@Component({
  selector: 'app-jd-status-dialog',
  standalone: true,
  imports: [CommonModule, MatDialogModule, MatButtonModule, MatProgressSpinnerModule, MatIconModule],
  template: `
    <div style="padding: 24px; min-width: 320px; text-align: center;">
      <h2 mat-dialog-title style="margin-bottom: 8px;">{{ statusText }}</h2>
      <mat-dialog-content>
        <div *ngIf="processing" style="display: flex; flex-direction: column; align-items: center; margin: 24px 0;">
          <mat-spinner diameter="48"></mat-spinner>
          <p style="margin-top: 16px; color: #666;">This may take up to a minute...</p>
        </div>

        <div *ngIf="completed" style="margin: 24px 0;">
          <mat-icon style="font-size: 64px; width: 64px; height: 64px; color: #4caf50;">check_circle</mat-icon>
        </div>

        <div *ngIf="failed" style="margin: 24px 0;">
          <mat-icon style="font-size: 64px; width: 64px; height: 64px; color: #f44336;">error</mat-icon>
        </div>

        <p *ngIf="message" style="margin-top: 16px;">{{ message }}</p>
      </mat-dialog-content>
      <mat-dialog-actions align="center" style="margin-top: 16px;">
        <button mat-button color="warn" *ngIf="processing" (click)="close()">Stop Processing</button>
        <button mat-raised-button color="primary" *ngIf="failed" (click)="close()">Close</button>
        <button mat-raised-button color="primary" *ngIf="completed" (click)="close()">Done</button>
      </mat-dialog-actions>
    </div>
  `
})
export class JdStatusDialogComponent {
  private dialogRef = inject(MatDialogRef<JdStatusDialogComponent>);
  private jobService = inject(JobService);
  private data = inject(MAT_DIALOG_DATA);
  private logger = inject(LoggerService);
  private cdr = inject(ChangeDetectorRef);

  statusText = 'Processing job description...';
  message = '';
  processing = true;
  failed = false;
  completed = false;
  private socket?: WebSocket;

  constructor() {
    this.connectWebSocket(this.data.jobId);
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
          this.statusText = data.status + '...';
        }
        if (data.completed) {
          this.processing = false;
          this.completed = true;
          this.statusText = 'Job processed successfully!';
          // Auto-close after a short delay
          setTimeout(() => {
            this.close();
            this.cdr.detectChanges();
          }, 1500);
        } else if (data.failed) {
          this.processing = false;
          this.failed = true;
          this.statusText = 'Processing failed';
          this.message = data.message || '';
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
      this.statusText = 'Connection error';
    };
  }

  close() {
    if (this.processing) {
      this.statusText = 'Stopping...';
      this.jobService.deleteJob(this.data.jobId).subscribe({
        next: () => {
          this.logger.log('Job deleted successfully');
          this.dialogRef.close('stopped');
        },
        error: (err) => {
          this.logger.error('Failed to delete job', err);
          this.dialogRef.close('stopped');
        }
      });
    } else {
      this.dialogRef.close('completed');
    }
  }

  // Add this to handle the navigation and reload in one place if needed,
  // but for now we'll stick to the dialog close and router navigation in onSubmit.
}

@Component({
  selector: 'app-create-job',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    RouterModule,
    MatButtonModule,
    MatFormFieldModule,
    MatSelectModule,
    MatInputModule,
    MatDialogModule,
    MatIconModule
  ],
  template: `
    <div class="create-job-container">
      <div class="header-row">
        <h1>Create New Job</h1>
        <button mat-stroked-button color="primary" type="button" (click)="autoFill()">
          <mat-icon>magic_button</mat-icon> Auto Fill (Dev)
        </button>
      </div>

      <form (submit)="onSubmit($event)" class="job-form">
        <div class="left-col">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Job Description</mat-label>
            <textarea matInput [(ngModel)]="jobDescription" name="jobDescription" rows="18" placeholder="Paste the full job description here..." required></textarea>
            <mat-hint>Paste the job requirements, responsibilities, and benefits.</mat-hint>
          </mat-form-field>
        </div>

        <div class="right-col">
          <mat-form-field appearance="outline" class="full-width">
            <mat-label>Department</mat-label>
            <mat-select [(ngModel)]="department" name="department" required>
              <mat-option *ngFor="let dept of departments" [value]="dept">{{ dept }}</mat-option>
            </mat-select>
          </mat-form-field>

          <div class="actions">
            <button mat-flat-button color="primary" type="submit" [disabled]="!jobDescription || !department" class="submit-btn">
              <mat-icon>save</mat-icon> Analyze & Save Job
            </button>
            <a mat-button routerLink="/" class="cancel-btn">Cancel</a>
          </div>
        </div>
      </form>
    </div>
  `,
  styles: [`
    .create-job-container {
      max-width: 1000px;
      margin: 0 auto;
      background: var(--card-bg);
      padding: 40px;
      border-radius: 16px;
      box-shadow: var(--shadow);
      border: 1px solid var(--border-color);
    }
    .header-row {
      display: flex;
      justify-content: space-between;
      align-items: center;
      margin-bottom: 32px;
    }
    .header-row h1 {
      margin: 0;
      font-size: 1.8rem;
      font-weight: 800;
    }
    .job-form {
      display: flex;
      gap: 32px;
    }
    .left-col {
      flex: 2;
    }
    .right-col {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 16px;
    }
    .full-width {
      width: 100%;
    }
    .actions {
      display: flex;
      flex-direction: column;
      gap: 12px;
      margin-top: 8px;
    }
    .submit-btn {
      height: 48px;
      font-size: 1rem;
      width: 100%;
    }
    .cancel-btn {
      width: 100%;
    }
    @media (max-width: 768px) {
      .job-form {
        flex-direction: column;
      }
      .create-job-container {
        padding: 24px;
      }
    }
  `]
})
export class CreateJobComponent {
  private jobService = inject(JobService);
  private dialog = inject(MatDialog);
  private router = inject(Router);

  jobDescription = '';
  department = '';
  departments = [
    'Engineering', 'Product', 'Design', 'Marketing', 'Sales', 'HR', 'Infrastructure', 'General'
  ];

  autoFill() {
    this.department = 'Engineering';
    this.jobDescription = `About the job
Equifax is seeking a visionary Principal Engineer to lead the charge in revolutionizing our product embarking on a transformation journey. You will be the single-threaded owner responsible for transforming our software development lifecycle (SDLC) by orchestrating and extending the capabilities of GitHub Copilot. The ultimate goal is to create a highly leveraged engineering organization where Copilot acts as a true autonomous agent, handling complex tasks from code generation and testing to incident response and documentation, all while operating within a well-defined, observable, and secure framework you own.

This role requires being in the office 3 days/week on Tues - Thurs.

This position does not offer immigration sponsorship (current or future) including F-1 STEM OPT extension support.

What You'll Do

Define the strategic roadmap for the platform with GitHub Copilot, treating it as a first-class internal product. Architect the complete system for Copilot's invocation, context retrieval, and action execution using custom tools.
Design and manage the Model Context Protocol (MCP) toolset, enabling Copilot's interaction with third-party services like ServiceNow, Atlassian, DataDog, and GCP for context and action.
Engineer the strategy for providing scalable context to GitHub Copilot, shaping its persona and behavior by translating internal engineering standards into a centralized, version-controlled repository of custom instructions and integrating vendor-provided connectors for various contexts.
Design, test, and refine complex prompts and contextual data frameworks to ensure our coding agents perform with maximum accuracy, efficiency, and reliability.
Define and monitor key performance indicators (KPIs) for the agentic system's effectiveness and implement a robust observability stack to track Copilot's interactions for continuous optimization.
Establish the platform's security posture by implementing safeguards for custom tools and APIs exposed to Copilot, and design a "human-in-the-loop" framework for critical actions
Define and enforce granular, code-driven permissions (RBAC) for the custom GitHub Actions and APIs that Copilot can invoke, ensuring the principle of least privilege.
Demonstrate a deep understanding of cloud native, distributed micro service based architectures
Deliver solutions for complex business problems through software standard SDLC
Build strong relationships with both internal and external stakeholders including product, business and sales partners
Demonstrate excellent communication skills with the ability to both simplify complex problems and also dive deeper if needed
Build and manage strong technical teams that deliver complex software solutions that scale
Provide deep troubleshooting skills with the ability to lead and solve production and customer issues under pressure
Leverage strong experience in full stack software development and public cloud like GCP and AWS
Mentor, coach and develop junior and other engineers
Lead with a data/metrics driven mindset with extreme focus towards optimizing and creating efficient solutions
Ensure compliance with EFX secure software development guidelines and best practices and responsible for meeting and maintaining QE, DevSec, and FinOps KPIs
Define, maintain and report SLA, SLO, SLIs meeting EFX engineering standards in partnership with the product, engineering and architecture teams
Collaborate with architects, SRE leads and other technical leadership on strategic technical direction, guidelines, and best practices
Drive up-to-date technical documentation including support, end user documentation and run books
Responsible for implementation architecture decision making associated with Product features/stories, refactoring work, and EOSL decisions
Create and deliver technical presentations to internal and external technical and non-technical stakeholders communicating with clarity and precision, and present complex information in a concise format that is audience appropriate

What You’ll Need

Bachelor's degree in Computer Science or equivalent experience
7+ years of hands on software engineering experience
7+ years experience writing, debugging, and troubleshooting code in mainstream Java, SpringBoot, TypeScript/JavaScript, HTML, CSS
7+ years experience designing and developing cloud-native solutions
7+ years experience designing and developing microservices using Java, SpringBoot, GCP SDKs, GKE/Kubernetes
3+ years of github copilot experience, preferably an expert.
3-5+ years of hands-on experience in building and architecting intelligent agent systems or platforms that integrate with LLMs.
Hands on experience deploying and releasing software using Github actions, Jenkins CI/CD pipelines, understand infrastructure-as-code concepts, Helm Charts, and Terraform constructs

What could set you apart

GitHub Ecosystem Mastery: Deep, hands-on expertise with the full GitHub platform, including GitHub Actions, GitHub Apps, webhooks, and the REST/GraphQL APIs.
Software Engineering Excellence: Senior-level proficiency in a language like Python, Go, or Node.js, with a deep understanding of software architecture and building scalable, maintainable services.
API and Integration Mastery: Demonstrable experience designing and consuming RESTful APIs and securely integrating disparate SaaS systems. Deep familiarity with the Model Context Protocol (MCP) and experience defining services that conform to its specification is a strong requirement.
Cloud-Native Proficiency: Deep familiarity with Google Cloud Platform (GCP), including Kubernetes, and IAM.
Systems Thinking: The ability to see the entire SDLC as an interconnected system and reason about how to inject Copilot for maximum leverage.
Event-Driven Architecture: Experience building systems that react to events, especially GitHub webhook events.
Applied LLM Expertise: Hands-on experience building applications that integrate with Large Language Models (LLMs), with a focus on practical application.
Tool-Use and Function-Calling Paradigm: A deep understanding of how to build and expose "tools" (APIs, functions, custom actions) for an LLM agent to consume.
Retrieable-Augmented Generation (RAG) Expert: Practical knowledge of designing, implementing, and optimizing RAG systems.
Pragmatic Agent Orchestration: The ability to orchestrate workflows around a pre-existing, powerful agent like Copilot.`;
  }

  onSubmit(event: Event) {
    event.preventDefault();
    if (!this.jobDescription || !this.department) return;

    this.jobService.saveJob(this.jobDescription, this.department).subscribe(res => {
      if (res.success) {
        const dialogRef = this.dialog.open(JdStatusDialogComponent, {
          data: { jobId: res.job_id },
          disableClose: true
        });

        dialogRef.afterClosed().subscribe(result => {
          if (result === 'completed' || result === 'stopped') {
            this.router.navigate(['/']);
          }
        });
      }
    });
  }
}
