/**
 * These interfaces mirror the Pydantic models in backend/app/schemas.py.
 * The frontend never recalculates a score: it only displays what the API sends.
 */

export type ComponentKey =
  | 'required_skills'
  | 'semantic_match'
  | 'other_keywords'
  | 'project_experience'
  | 'education'
  | 'certifications'
  | 'soft_skills'

export interface MatchedItem {
  name: string
  evidence: string
  match_method: string
  confidence: number
  found_in: string
}

export interface SemanticEvidence {
  requirement: string
  requirement_type: string
  importance: number
  best_evidence: string
  similarity: number
  meets_threshold: boolean
  score: number
}

export interface Penalty {
  reason: string
  points: number
  detail: string
}

export interface BiasFlag {
  category: string
  message: string
  evidence: string
  severity: string
}

export interface FailedFile {
  filename: string
  error: string
  reason_code: string
}

export interface JobAnalysis {
  title: string
  required_skills: string[]
  preferred_skills: string[]
  other_keywords: string[]
  responsibilities: string[]
  required_qualifications: string[]
  preferred_qualifications: string[]
  education_requirements: string[]
  certification_requirements: string[]
  soft_skills: string[]
  experience_expectation: string
  requirement_statement_count: number
  semantic_requirement_count: number
  skill_confidence: Record<string, number>
  skill_sources: Record<string, string>
  analysis_notes: string[]
  bias_flags: BiasFlag[]
}

export interface ScoringInfo {
  base_weights: Record<string, number>
  effective_weights: Record<string, number>
  active_components: string[]
  inactive_components: string[]
  activation_reasons: Record<string, string>
  component_labels: Record<string, string>
}

export interface Candidate {
  rank: number
  candidate_id: string
  candidate_name: string
  filename: string
  final_score: number
  component_scores: Record<string, number>
  weighted_contributions: Record<string, number>
  matched_required_skills: MatchedItem[]
  matched_other_keywords: MatchedItem[]
  required_skills_not_found: string[]
  other_keywords_not_found: string[]
  semantic_evidence: SemanticEvidence[]
  project_experience_evidence: SemanticEvidence[]
  education_evidence: MatchedItem[]
  certification_evidence: MatchedItem[]
  soft_skill_evidence: MatchedItem[]
  education_not_found: string[]
  certifications_not_found: string[]
  soft_skills_not_found: string[]
  penalties: Penalty[]
  whole_document_similarity: number | null
  explanation: string
  warnings: string[]
}

export interface RankSummary {
  total_candidates: number
  successfully_processed: number
  failed_files: FailedFile[]
}

export interface ModelInfo {
  name: string
  backend: string
  note: string
}

export interface RankResponse {
  result_id: string
  job: JobAnalysis
  scoring: ScoringInfo
  summary: RankSummary
  candidates: Candidate[]
  model: ModelInfo
}

export interface AnalyzeJDResponse {
  job: JobAnalysis
  scoring: ScoringInfo
}

export interface ComponentDifference {
  component: string
  label: string
  candidate_a_score: number
  candidate_b_score: number
  difference: number
  effective_weight: number
  weighted_difference: number
}

export interface CompareResponse {
  result_id: string
  candidate_a_id: string
  candidate_b_id: string
  candidate_a_name: string
  candidate_b_name: string
  candidate_a_final_score: number
  candidate_b_final_score: number
  final_score_difference: number
  component_differences: ComponentDifference[]
  only_a_required_skills: string[]
  only_b_required_skills: string[]
  shared_required_skills: string[]
  only_a_other_keywords: string[]
  only_b_other_keywords: string[]
  a_requirements_not_found: string[]
  b_requirements_not_found: string[]
  a_best_evidence: string[]
  b_best_evidence: string[]
  explanation: string
}

export interface HealthResponse {
  status: string
  version: string
  semantic_model_status: string
  model_name: string
  model_backend: string
  taxonomy_version: string
  detail: string
}

export const COMPONENT_ORDER: ComponentKey[] = [
  'required_skills',
  'semantic_match',
  'other_keywords',
  'project_experience',
  'education',
  'certifications',
  'soft_skills',
]

export const COMPONENT_COLORS: Record<string, string> = {
  required_skills: '#1F6F5C',
  semantic_match: '#2A4E8F',
  other_keywords: '#4C8C7B',
  project_experience: '#3D6EA8',
  education: '#7A9A4F',
  certifications: '#B4651A',
  soft_skills: '#8A6FA8',
}

export const SHORT_LABELS: Record<string, string> = {
  required_skills: 'Required skills',
  semantic_match: 'Semantic',
  other_keywords: 'Other keywords',
  project_experience: 'Projects & experience',
  education: 'Education',
  certifications: 'Certifications',
  soft_skills: 'Soft skills',
}
