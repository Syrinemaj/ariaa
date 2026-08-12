import { api } from './api'

// ── Types ─────────────────────────────────────────────────────────────────────

export interface Team {
  id: string
  org_id: string
  name: string
  member_count: number
  member_user_ids: string[]
  created_at?: string
}

export interface TeamMember {
  id: string
  full_name: string
  email: string
  role: string
}

export interface TeamDetail extends Team {
  members: TeamMember[]
}

// ── API calls ─────────────────────────────────────────────────────────────────

export function listTeams() {
  return api.get<{ teams: Team[] }>('/teams').then(r => r.teams)
}

export function createTeam(name: string) {
  return api.post<Team>('/teams', { name })
}

export function getTeam(id: string) {
  return api.get<TeamDetail>(`/teams/${id}`)
}

export function renameTeam(id: string, name: string) {
  return api.patch<Team>(`/teams/${id}`, { name })
}

export function deleteTeam(id: string) {
  return api.del(`/teams/${id}`)
}

export function addTeamMember(teamId: string, userId: string) {
  return api.post<{ team_id: string; user_id: string }>(`/teams/${teamId}/members`, { user_id: userId })
}

export function removeTeamMember(teamId: string, userId: string) {
  return api.del(`/teams/${teamId}/members/${userId}`)
}
