import { Injectable, inject } from '@angular/core';
import { HttpClient } from '@angular/common/http';
import { Observable } from 'rxjs';

export interface Resume {
  id: string;
  original_filename: string;
  structured_data?: any;
  job_id: string;
  analysis_id?: string;
  analysis?: any;
}

export interface Job {
  id: string;
  job_title: string;
  department: string;
  markdown_text: string;
  resumes: Resume[];
}

@Injectable({
  providedIn: 'root'
})
export class JobService {
  private http = inject(HttpClient);
  private apiUrl = '/api/v1';

  getJobs(): Observable<Job[]> {
    return this.http.get<Job[]>(`${this.apiUrl}/jobs`);
  }

  getResume(resumeId: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/resumes/${resumeId}`);
  }

  uploadResume(jobId: string, file: File): Observable<any> {
    const formData = new FormData();
    formData.append('job_id', jobId);
    formData.append('resume', file);
    return this.http.post(`${this.apiUrl}/resumes/upload`, formData);
  }

  saveJob(jobDescription: string, department: string): Observable<any> {
    const formData = new FormData();
    formData.append('job_description', jobDescription);
    formData.append('department', department);
    return this.http.post(`${this.apiUrl}/jobs/save`, formData);
  }

  getJob(jobId: string): Observable<any> {
    // Note: The backend doesn't have a single job GET endpoint yet,
    // but we can find it in getJobs() or implement it if needed.
    // For now, let's assume it exists or we use getJobs and filter.
    // Actually, looking at router.py, there is no GET /v1/jobs/{id}.
    // I'll add a placeholder and check if I should add the endpoint to backend.
    return this.http.get<any>(`${this.apiUrl}/jobs/${jobId}`);
  }

  getAnalysis(resumeId: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/resume/${resumeId}/analysis`);
  }

  getAnalysisById(analysisId: string): Observable<any> {
    return this.http.get<any>(`${this.apiUrl}/analysis/${analysisId}`);
  }

  getResumePdfUrl(resumeId: string): string {
    return `${this.apiUrl}/resumes/${resumeId}/pdf`;
  }

  stopResumeProcessing(jobId: string): Observable<any> {
    return this.http.post<any>(`${this.apiUrl}/resumes/stop/${jobId}`, {});
  }

  deleteJob(jobId: string): Observable<any> {
    return this.http.delete<any>(`${this.apiUrl}/jobs/${jobId}`);
  }
}
