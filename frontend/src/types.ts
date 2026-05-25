// Shared TypeScript types for the Fake News Detector frontend

export interface FactCheckResult {
  claim: string
  rating: string
  source: string
}

export interface PredictionResponse {
  id: string
  label: 'Real' | 'Fake'
  confidence: number
  suspicious_phrases: string[]
  explanation: string
  fact_checks: FactCheckResult[]
  trust_rating: 'High' | 'Medium' | 'Low' | 'Unknown' | null
  language: string
  timestamp: string
  input_text?: string
  input_url?: string | null
}
