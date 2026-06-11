// All API calls go through this file.
// The base URL switches based on vault mode (local vs remote).

function getBase() {
  const mode = localStorage.getItem('vaultMode') ||
    (window.location.hostname === 'localhost' ? 'local' : 'remote')
  if (mode === 'local') return 'http://localhost:8000'
  if (window.location.hostname !== 'localhost') return '/api'
  const remote = localStorage.getItem('remoteVaultUrl') || ''
  return remote ? `${remote}/api` : '/api'
}

// Watch/browse always talks to the local vault — it reads the local filesystem
// regardless of which vault mode the UI is in.
const LOCAL_BASE = 'http://localhost:8000'

async function req(method, path, body) {
  const opts = { method, headers: {} }
  if (body && !(body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  } else if (body) {
    opts.body = body  // FormData — browser sets Content-Type automatically
  }
  const res = await fetch(`${getBase()}${path}`, opts)
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.status === 204 ? null : res.json()
}

// Repositories
export const listRepos = () => req('GET', '/repos/')
export const createRepo = body => req('POST', '/repos/', body)
export const getRepo = id => req('GET', `/repos/${id}`)
export const deleteRepo = id => req('DELETE', `/repos/${id}`)
export const linkRepo = (id, remoteUrl) => req('PATCH', `/repos/${id}`, { remote_url: remoteUrl })

// Documents
export const listDocuments = repoId => req('GET', `/repos/${repoId}/documents/`)
export const createDocument = (repoId, body) => req('POST', `/repos/${repoId}/documents/`, body)
export const getDocument = (repoId, docId) => req('GET', `/repos/${repoId}/documents/${docId}`)
export const editDocument = (repoId, docId, body) => req('PATCH', `/repos/${repoId}/documents/${docId}`, body)
export const getDocumentBom = (repoId, docId) => req('GET', `/repos/${repoId}/documents/${docId}/bom`)
export const getDocumentLatestCommit = (repoId, docId) => req('GET', `/repos/${repoId}/documents/${docId}/latest-commit`)
export const uploadDocument = (repoId, docId, formData) =>
  req('POST', `/repos/${repoId}/documents/${docId}/upload`, formData)
// returns all versions of a document with presigned PDF URLs for each version and the one before it
export const getDocumentCommits = (repoId, docId) =>
  req('GET', `/repos/${repoId}/documents/${docId}/commits`)

// Commits
export const getLog = (repoId, limit = 50, branchId = null) =>
  req('GET', `/repos/${repoId}/log?limit=${limit}${branchId ? `&branch_id=${branchId}` : ''}`)
export const getDiff = (repoId, hash) => req('GET', `/repos/${repoId}/diff/${hash}`)
export const createCommit = (repoId, formData) => req('POST', `/repos/${repoId}/commit`, formData)
export const amendCommit = (repoId, shortHash, body) => req('PATCH', `/repos/${repoId}/commits/${shortHash}`, body)

// Branches
export const listBranches = repoId => req('GET', `/repos/${repoId}/branches/`)
export const createBranch = (repoId, body) => req('POST', `/repos/${repoId}/branches/`, body)
export const getMergeRequest = (repoId, branchId) =>
  req('POST', `/repos/${repoId}/branches/${branchId}/merge-request`)
export const executeMerge = (repoId, branchId, author) =>
  req('POST', `/repos/${repoId}/branches/${branchId}/merge?author=${encodeURIComponent(author)}`)

// Product tree
export const getTree = repoId => req('GET', `/repos/${repoId}/tree`)
export const validateTree = repoId => req('GET', `/repos/${repoId}/tree/validate`)
export const addBomEntry = (repoId, assemblyId, body) =>
  req('POST', `/repos/${repoId}/bom?assembly_id=${assemblyId}`, body)
export const removeBomEntry = (repoId, entryId) => req('DELETE', `/repos/${repoId}/bom/${entryId}`)

// Sync
export const syncStatus = repoId => req('GET', `/sync/status/${repoId}`)
export const push = repoId => req('POST', `/sync/push/${repoId}`)
export const pull = repoId => req('POST', `/sync/pull/${repoId}`)

// Audit
export const getAudit = (repoId, params = '') => req('GET', `/repos/${repoId}/audit${params}`)
export const getBreaches = repoId => req('GET', `/repos/${repoId}/audit/breaches`)
export const getDocumentHistory = (repoId, docId) =>
  req('GET', `/repos/${repoId}/documents/${docId}/history`)

// Working directory
export const getWatchStatus = repoId => req('GET', `/repos/${repoId}/watch/status`)
export const watchCommit = (repoId, formData) => req('POST', `/repos/${repoId}/watch/commit`, formData)
// browseWatch and watchPreviewUrl always use LOCAL_BASE — they access the local filesystem
export const browseWatch = (path = '') =>
  fetch(`${LOCAL_BASE}/watch/browse${path ? `?path=${encodeURIComponent(path)}` : ''}`)
    .then(r => r.ok ? r.json() : r.json().then(e => Promise.reject(new Error(e.detail || r.statusText))))
export const watchPreviewUrl = (repoId, filename) => `${LOCAL_BASE}/repos/${repoId}/watch/preview/${encodeURIComponent(filename)}`
