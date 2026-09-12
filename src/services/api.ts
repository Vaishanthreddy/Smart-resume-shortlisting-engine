/** Centralised Axios client. The backend URL comes from the environment. */
import axios, { AxiosError } from 'axios'
import type {
  AnalyzeJDResponse,
  CompareResponse,
  HealthResponse,
  RankResponse,
} from '../types'

const baseURL = import.meta.env.VITE_API_BASE_URL ?? 'http://localhost:8000'

export const client = axios.create({
  baseURL,
  timeout: 300_000,
})

/** Turn any failure into a sentence a recruiter can act on. */
export function readError(error: unknown): string {
  const axiosError = error as AxiosError<{ detail?: string }>
  if (axiosError?.response?.data?.detail) return axiosError.response.data.detail
  if (axiosError?.code === 'ECONNABORTED') {
    return 'The request timed out. Try again with fewer resumes at once.'
  }
  if (axiosError?.request && !axiosError.response) {
    return `No response from the backend at ${baseURL}. Start it with: uvicorn app.main:app --reload --port 8000`
  }
  if (axiosError?.message) return axiosError.message
  return 'Something went wrong. Try again.'
}

export async function getHealth(): Promise<HealthResponse> {
  const { data } = await client.get<HealthResponse>('/api/health')
  return data
}

export async function analyzeJd(jdFile: File): Promise<AnalyzeJDResponse> {
  const form = new FormData()
  form.append('jd_file', jdFile)
  const { data } = await client.post<AnalyzeJDResponse>('/api/analyze-jd', form)
  return data
}

export async function rankResumes(jdFile: File, resumes: File[]): Promise<RankResponse> {
  const form = new FormData()
  form.append('jd_file', jdFile)
  resumes.forEach((file) => form.append('resume_files', file))
  const { data } = await client.post<RankResponse>('/api/rank', form)
  return data
}

export async function compareCandidates(
  resultId: string,
  candidateAId: string,
  candidateBId: string,
): Promise<CompareResponse> {
  const { data } = await client.post<CompareResponse>('/api/compare', {
    result_id: resultId,
    candidate_a_id: candidateAId,
    candidate_b_id: candidateBId,
  })
  return data
}

export { baseURL }
