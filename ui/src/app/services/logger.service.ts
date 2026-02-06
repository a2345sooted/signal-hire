import { Injectable } from '@angular/core';

@Injectable({
  providedIn: 'root'
})
export class LoggerService {
  log(message: string, data?: any) {
    if (data) {
      console.log(`[SignalHire] ${message}`, data);
    } else {
      console.log(`[SignalHire] ${message}`);
    }
  }

  error(message: string, error?: any) {
    if (error) {
      console.error(`[SignalHire] ERROR: ${message}`, error);
    } else {
      console.error(`[SignalHire] ERROR: ${message}`);
    }
  }

  warn(message: string, data?: any) {
    if (data) {
      console.warn(`[SignalHire] WARN: ${message}`, data);
    } else {
      console.warn(`[SignalHire] WARN: ${message}`);
    }
  }

  debug(message: string, data?: any) {
    if (data) {
      console.debug(`[SignalHire] DEBUG: ${message}`, data);
    } else {
      console.debug(`[SignalHire] DEBUG: ${message}`);
    }
  }
}
