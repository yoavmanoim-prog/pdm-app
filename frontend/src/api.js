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

// Auth + user management always resolve against the REMOTE user store, NOT the
// Local/Remote data toggle. On the deployed site this is the remote vault itself
// (same-origin /api). On a local workstation it goes through the local vault on
// :8000, which forwards auth to whatever REMOTE_VAULT_URL points at — so login
// always hits the one shared user store regardless of which vault you're browsing.
function authBase() {
  if (window.location.hostname !== 'localhost') return '/api'
  return 'http://localhost:8000'
}

// Watch/browse always talks to the local vault — it reads the local filesystem
// regardless of which vault mode the UI is in.
const LOCAL_BASE = 'http://localhost:8000'

// where the login token lives. The backend stamps every request's identity from
// the JWT in the Authorization header, so we attach it to every call below.
const TOKEN_KEY = 'authToken'
export const getToken = () => localStorage.getItem(TOKEN_KEY)
export const setToken = t => t ? localStorage.setItem(TOKEN_KEY, t) : localStorage.removeItem(TOKEN_KEY)

function authHeaders() {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

async function req(method, path, body, base = getBase()) {
  const opts = { method, headers: { ...authHeaders() } }
  if (body && !(body instanceof FormData)) {
    opts.headers['Content-Type'] = 'application/json'
    opts.body = JSON.stringify(body)
  } else if (body) {
    opts.body = body  // FormData — browser sets Content-Type automatically
  }
  const res = await fetch(`${base}${path}`, opts)
  if (!res.ok) {
    // 401 anywhere except the login/signup calls themselves means our token is
    // missing or expired — drop it and bounce to the login screen.
    if (res.status === 401 && !path.startsWith('/auth/')) {
      setToken(null)
      if (window.location.pathname !== '/login') window.location.assign('/login')
    }
    const err = await res.json().catch(() => ({ detail: res.statusText }))
    throw new Error(typeof err.detail === 'string' ? err.detail : JSON.stringify(err.detail))
  }
  return res.status === 204 ? null : res.json()
}

// Auth + users always go to the shared user store (authBase), independent of the
// data-vault toggle — so the login page works no matter which vault is selected.
const authReq = (method, path, body) => req(method, path, body, authBase())
export const signup = body => authReq('POST', '/auth/signup', body)
export const login = body => authReq('POST', '/auth/login', body)
export const getMe = () => authReq('GET', '/auth/me')
export const listUsers = () => authReq('GET', '/users')
export const createUser = body => authReq('POST', '/users', body)
export const updateUser = (id, body) => authReq('PATCH', `/users/${id}`, body)
export const deleteUser = id => authReq('DELETE', `/users/${id}`)

// Repositories
export const listRepos = () => req('GET', '/repos/')
export const createRepo = body => req('POST', '/repos/', body)
export const getRepo = id => req('GET', `/repos/${id}`)
export const deleteRepo = id => req('DELETE', `/repos/${id}`)
export const linkRepo = (id, remoteUrl, remoteRepoId = null) =>
  req('PATCH', `/repos/${id}`, { remote_url: remoteUrl, remote_repo_id: remoteRepoId })
// list repos on a remote vault so the user can pick which one to link to
export const listRemoteRepos = remoteUrl =>
  req('GET', `/sync/remote-repos?remote_url=${encodeURIComponent(remoteUrl)}`)
// per-repo settings (e.g. part-number format derived from a sample)
export const getRepoSettings = id => req('GET', `/repos/${id}/settings`)
export const updateRepoSettings = (id, body) => req('PUT', `/repos/${id}/settings`, body)

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

// Release requests
export const createReleaseRequest = (repoId, docId, body) =>
  req('POST', `/repos/${repoId}/documents/${docId}/release-request`, body)
export const listReleaseRequests = repoId => req('GET', `/repos/${repoId}/release-requests`)
export const approveReleaseRequest = (repoId, reqId, body) =>
  req('POST', `/repos/${repoId}/release-requests/${reqId}/approve`, body)
export const denyReleaseRequest = (repoId, reqId, body) =>
  req('POST', `/repos/${repoId}/release-requests/${reqId}/deny`, body)

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
