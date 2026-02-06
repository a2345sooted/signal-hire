import { Routes } from '@angular/router';
import { ResumeAnalysisComponent } from './resume-analysis/resume-analysis.component';
import { ResumeUploadComponent } from './resume-upload/resume-upload.component';
import { CreateJobComponent } from './create-job/create-job.component';

export const routes: Routes = [
  { path: 'resume/:id/analysis', component: ResumeAnalysisComponent },
  { path: 'analysis/:id', component: ResumeAnalysisComponent },
  { path: 'resume/upload/:jobId', component: ResumeUploadComponent },
  { path: 'jobs/create', component: CreateJobComponent }
];
