import { useEffect, useRef, useState, useCallback } from 'react'
import './App.css'

// ─── Types ────────────────────────────────────────────────────────────
type Signal = 'UP' | 'DOWN' | 'WAIT'
type Page = 'dashboard' | 'signals' | 'history' | 'admin' | 'backtest'
type AdminTab = 'overview' | 'licenses' | 'users' | 'security'
type MarketTab = 'quotex' | 'forex' | 'crypto'

interface SignalResponse {
  pair: string; current_price: number; signal: Signal
  confidence: number; duration: string; market_trend: string
  status: string; analysis: string[]
  data_source?: string; data_warning?: string | null
}

interface LicenseSession {
  token: string; user_id: number; username: string
  license_key: string; expires_at: string; device_id: string
}

interface AdminSession { token: string }

interface LicenseRow {
  id: number; key: string; owner: string; device_id: string | null
  expires_at: string; is_active: number; activated_at: string | null
}

interface UserRow {
  id: number; username: string; email: string
  created_at: string; is_active: number
  subscription_tier: string; subscription_expires_at: string | null
}

interface HistoryRow {
  id: number; created_at: string; mode: string; pair: string
  signal: string; confidence: number; duration: string; market_trend: string
  outcome: string | null
}

interface DashboardStats {
  total_users: number; active_users: number
  expired_licenses: number; online_users: number
  total_licenses: number; active_licenses: number
}

// ─── Constants ────────────────────────────────────────────────────────
const API = import.meta.env.VITE_API_BASE_URL ?? '/api'

const WHATSAPP_URL = `https://wa.me/923224914560?text=${encodeURIComponent('Hello, I want to purchase an API/License Key.')}`

// Minimum confidence required to give a directional signal (UP/DOWN)
const MIN_CONFIDENCE = 65

const QUOTEX_PAIRS = [
  'EUR/USD', 'GBP/USD', 'USD/JPY', 'AUD/USD', 'USD/CHF', 'EUR/GBP',
  'USD/CAD', 'NZD/USD', 'EUR/JPY', 'GBP/JPY', 'AUD/JPY', 'EUR/CHF',
  'EUR/USD (OTC)', 'GBP/USD (OTC)', 'USD/JPY (OTC)', 'AUD/USD (OTC)',
  'USD/CHF (OTC)', 'EUR/GBP (OTC)', 'USD/CAD (OTC)', 'NZD/USD (OTC)',
  'EUR/JPY (OTC)', 'GBP/JPY (OTC)', 'AUD/JPY (OTC)', 'EUR/CHF (OTC)'
]

const QUOTEX_OTC = QUOTEX_PAIRS.filter(p => p.includes('OTC'))
const QUOTEX_LIVE = QUOTEX_PAIRS.filter(p => !p.includes('OTC'))
const ALL_QUOTEX = QUOTEX_PAIRS

const FOREX_PAIRS = QUOTEX_PAIRS
const CRYPTO_PAIRS = QUOTEX_PAIRS

const ALL_PAIRS = QUOTEX_PAIRS

const DURATIONS = ['5 Seconds','10 Seconds','15 Seconds','30 Seconds','1 Minute','5 Minutes']

// ─── Helpers ──────────────────────────────────────────────────────────
function getDeviceId(): string {
  let id = localStorage.getItem('device_id')
  if (!id) {
    id = 'dev_' + crypto.randomUUID()
    localStorage.setItem('device_id', id)
  }
  return id
}

function fmtDate(s: string | null) {
  if (!s) return '—'
  const d = new Date(s)
  return isNaN(d.getTime()) ? s : d.toLocaleDateString('en-PK', { year: 'numeric', month: 'short', day: 'numeric' })
}

function confClass(c: number) {
  if (c >= 75) return 'conf-high'
  if (c >= 50) return 'conf-medium'
  return 'conf-low'
}

// ─── Custom Scrollable Dropdown (Always opens DOWNWARDS with Search) ────────
function CustomDropdown({
  options,
  value,
  onChange,
  searchable = true
}: {
  options: string[]
  value: string
  onChange: (val: string) => void
  searchable?: boolean
}) {
  const [isOpen, setIsOpen] = useState(false)
  const [search, setSearch] = useState('')
  const dropdownRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    function handleClickOutside(e: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(e.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  const filtered = searchable && search.trim()
    ? options.filter(o => o.toLowerCase().includes(search.toLowerCase()))
    : options

  return (
    <div ref={dropdownRef} className="custom-dropdown-container">
      <button
        type="button"
        className="custom-dropdown-trigger"
        onClick={() => setIsOpen(!isOpen)}
      >
        <span>{value}</span>
        <span style={{ fontSize: 11, opacity: 0.8, transform: isOpen ? 'rotate(180deg)' : 'rotate(0deg)', transition: 'transform 0.2s' }}>▼</span>
      </button>

      {isOpen && (
        <div className="custom-dropdown-menu">
          {searchable && (
            <input
              type="text"
              className="custom-dropdown-search"
              placeholder="🔍 Search pair..."
              value={search}
              onChange={e => setSearch(e.target.value)}
              autoFocus
            />
          )}
          <div className="custom-dropdown-list">
            {filtered.length > 0 ? (
              filtered.map(opt => (
                <button
                  key={opt}
                  type="button"
                  className={`custom-dropdown-item ${opt === value ? 'selected' : ''}`}
                  onClick={() => {
                    onChange(opt)
                    setIsOpen(false)
                    setSearch('')
                  }}
                >
                  <span>{opt}</span>
                  {opt === value && <span style={{ color: 'var(--accent-purple)', fontWeight: 800 }}>✓</span>}
                </button>
              ))
            ) : (
              <div style={{ padding: '12px', fontSize: '12px', color: 'var(--text-muted)', textAlign: 'center' }}>
                No pair found
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
//  APP
// ═══════════════════════════════════════════════════════════════════════
export default function App() {
  // Session state
  const [userSession, setUserSession] = useState<LicenseSession | null>(null)
  const [adminSession, setAdminSession] = useState<AdminSession | null>(null)
  const [page, setPage] = useState<Page>('dashboard')
  const [sidebarOpen, setSidebarOpen] = useState(false)

  // Try auto-login from localStorage
  useEffect(() => {
    const saved = localStorage.getItem('user_session')
    if (saved) {
      try { setUserSession(JSON.parse(saved)) } catch { /* ignore */ }
    }
    const adminSaved = localStorage.getItem('admin_session')
    if (adminSaved) {
      try { setAdminSession(JSON.parse(adminSaved)) } catch { /* ignore */ }
    }
  }, [])

  // Heartbeat every 2 min while logged in
  useEffect(() => {
    if (!userSession) return
    const interval = setInterval(() => {
      fetch(`${API}/user/heartbeat`, {
        method: 'POST',
        headers: { 'x-user-token': userSession.token },
      }).catch(() => {})
    }, 120_000)
    // Send one immediately
    fetch(`${API}/user/heartbeat`, {
      method: 'POST',
      headers: { 'x-user-token': userSession.token },
    }).catch(() => {})
    return () => clearInterval(interval)
  }, [userSession])

  const handleUserLogin = (session: LicenseSession) => {
    setUserSession(session)
    localStorage.setItem('user_session', JSON.stringify(session))
  }

  const handleAdminLogin = (session: AdminSession) => {
    setAdminSession(session)
    localStorage.setItem('admin_session', JSON.stringify(session))
    setPage('admin')
  }

  const handleLogout = () => {
    setUserSession(null)
    setAdminSession(null)
    localStorage.removeItem('user_session')
    localStorage.removeItem('admin_session')
    setPage('dashboard')
  }

  // ─── NOT LOGGED IN → Show Login ──────────────────────────────────────
  if (!userSession && !adminSession) {
    return <LoginScreen onUserLogin={handleUserLogin} onAdminLogin={handleAdminLogin} />
  }

  const isAdmin = !!adminSession
  const username = userSession?.username ?? 'Shahzaib'

  return (
    <div className="app-layout">
      {/* Mobile header */}
      <div className="mobile-header">
        <button className="mobile-menu-btn" onClick={() => setSidebarOpen(!sidebarOpen)}>☰</button>
        <span style={{ fontWeight: 700, fontSize: 16 }}>Trading Bot</span>
      </div>

      {/* Sidebar overlay for mobile */}
      {sidebarOpen && <div className="sidebar-overlay" onClick={() => setSidebarOpen(false)} />}

      {/* Sidebar */}
      <aside className={`sidebar ${sidebarOpen ? 'open' : ''}`}>
        <div className="sidebar-brand">
          <div className="sidebar-brand-icon" style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
            <IconChart size={20} />
          </div>
          <div>
            <div className="sidebar-brand-text">Trading Bot</div>
            <div className="sidebar-brand-sub">AI Signal Engine</div>
          </div>
        </div>

        <nav className="sidebar-nav">
          <div className="sidebar-section-label">Main</div>
          <button className={`sidebar-link ${page === 'dashboard' ? 'active' : ''}`} onClick={() => { setPage('dashboard'); setSidebarOpen(false) }} style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
            <IconHome size={16} /> Dashboard
          </button>
          <button className={`sidebar-link ${page === 'signals' ? 'active' : ''}`} onClick={() => { setPage('signals'); setSidebarOpen(false) }} style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
            <IconActivity size={16} /> Generate Signal
          </button>
          <button className={`sidebar-link ${page === 'history' ? 'active' : ''}`} onClick={() => { setPage('history'); setSidebarOpen(false) }} style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
            <IconClipboard size={16} /> Trade History
          </button>

          {isAdmin && (
            <>
              <div className="sidebar-section-label">Admin</div>
              <button className={`sidebar-link ${page === 'admin' ? 'active' : ''}`} onClick={() => { setPage('admin'); setSidebarOpen(false) }} style={{ display: 'inline-flex', alignItems: 'center', gap: 12 }}>
                <IconSettings size={16} /> Admin Panel
              </button>
            </>
          )}
        </nav>

        <div className="sidebar-user">
          <div className="sidebar-avatar">{username[0]?.toUpperCase()}</div>
          <div className="sidebar-user-info">
            <div className="sidebar-username">{username}</div>
            <div className="sidebar-user-role">{isAdmin ? 'Administrator' : 'Licensed User'}</div>
          </div>
          <button className="sidebar-logout" onClick={handleLogout} title="Logout" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
            <IconLogout size={16} />
          </button>
        </div>
      </aside>

      {/* Main content */}
      <main className="main-content">
        {page === 'dashboard' && <DashboardPage session={userSession} adminSession={adminSession} />}
        {page === 'signals' && <SignalsPage session={userSession} adminSession={adminSession} />}
        {page === 'history' && <HistoryPage session={userSession} adminSession={adminSession} />}
        {page === 'backtest' && <BacktestPage adminSession={adminSession} />}
        {page === 'admin' && isAdmin && <AdminPage adminSession={adminSession} />}
      </main>

      {/* WhatsApp FAB */}
      <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="whatsapp-fab" title="Contact Developer on WhatsApp">
        <IconMessageSquare size={26} />
      </a>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
//  LOGIN SCREEN
// ═══════════════════════════════════════════════════════════════════════
function LoginScreen({ onUserLogin, onAdminLogin }: {
  onUserLogin: (s: LicenseSession) => void
  onAdminLogin: (s: AdminSession) => void
}) {
  const [tab, setTab] = useState<'license' | 'admin'>('license')
  const [licenseKey, setLicenseKey] = useState('')
  const [userEmail, setUserEmail] = useState('')
  const [adminPass, setAdminPass] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')

  // Password reset fields
  const [showReset, setShowReset] = useState(false)
  const [recoveryKey, setRecoveryKey] = useState('')
  const [newAdminPass, setNewAdminPass] = useState('')

  const handleLicenseLogin = async () => {
    if (!licenseKey.trim()) { setError('Please enter your license key.'); return }
    if (!userEmail.trim()) { setError('Please enter your registered Gmail/Email.'); return }
    setLoading(true); setError(''); setSuccess('')
    try {
      const deviceId = getDeviceId()
      const res = await fetch(`${API}/license/verify`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ 
          license_key: licenseKey.trim(), 
          device_id: deviceId,
          email: userEmail.trim()
        }),
      })
      const data = await res.json()
      if (data.status === 'valid') {
        setSuccess(data.message)
        setTimeout(() => {
          onUserLogin({
            token: data.token,
            user_id: data.user_id,
            username: data.username,
            license_key: licenseKey.trim(),
            expires_at: data.expires_at,
            device_id: deviceId,
          })
        }, 800)
      } else if (data.status === 'expired') {
        setError('⏰ License Expired. Please contact admin to renew your license.')
      } else if (data.status === 'suspended') {
        setError('🚨 Security Violation Detected! Your account has been SUSPENDED due to unauthorized device or Gmail usage. Contact admin immediately.')
      } else if (data.status === 'device_mismatch') {
        setError('🔒 ' + (data.message || 'License is already bound to another device or Gmail.'))
      } else {
        setError(data.message || 'Invalid License Key.')
      }
    } catch {
      setError('Connection failed. Make sure the backend is running.')
    }
    setLoading(false)
  }

  const handleAdminLogin = async () => {
    if (!adminPass.trim()) { setError('Please enter the admin password.'); return }
    setLoading(true); setError('')
    try {
      const res = await fetch(`${API}/admin/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ password: adminPass }),
      })
      if (!res.ok) {
        const err = await res.json()
        setError(err.detail || 'Invalid admin password.')
        setLoading(false)
        return
      }
      const data = await res.json()
      onAdminLogin({ token: data.token })
    } catch {
      setError('Connection failed. Make sure the backend is running.')
    }
    setLoading(false)
  }

  const handleResetPassword = async () => {
    if (!recoveryKey.trim()) { setError('Please enter your Secret Recovery Key.'); return }
    if (!newAdminPass.trim() || newAdminPass.length < 6) { setError('New password must be at least 6 characters.'); return }
    setLoading(true); setError(''); setSuccess('')
    try {
      const res = await fetch(`${API}/admin/reset-password`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          recovery_key: recoveryKey.trim(),
          new_password: newAdminPass.trim()
        }),
      })
      const data = await res.json()
      if (res.ok) {
        setSuccess('Admin password reset successfully! You can now log in.')
        setAdminPass('')
        setRecoveryKey('')
        setNewAdminPass('')
        setTimeout(() => {
          setShowReset(false)
          setSuccess('')
        }, 2000)
      } else {
        setError(data.detail || 'Failed to reset password. Check recovery phrase.')
      }
    } catch {
      setError('Connection failed. Make sure the backend is running.')
    }
    setLoading(false)
  }

  return (
    <div className="login-container">
      <div className="login-card">
        <div className="login-logo">
          <div className="login-logo-icon" style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', color: 'white' }}>
            <IconChart size={28} />
          </div>
          <div className="login-title">Trading Bot</div>
        </div>
        <div className="login-subtitle">AI-Powered Signal Engine for Quotex</div>

        {showReset ? (
          <>
            <div style={{ fontWeight: 700, fontSize: 15, color: 'var(--accent-purple)', marginBottom: 12 }}>🔒 Reset Admin Password</div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', marginBottom: 16 }}>
              Enter the Secret Recovery Key printed in your backend server logs during database seeding.
            </p>

            {error && <div className="login-error">{error}</div>}
            {success && <div className="login-success">{success}</div>}

            <div className="login-field">
              <label>Secret Recovery Key</label>
              <input
                type="text"
                placeholder="sb_recovery_xxxxxxxxxxxxxxxx"
                value={recoveryKey}
                onChange={e => setRecoveryKey(e.target.value)}
              />
            </div>

            <div className="login-field">
              <label>New Admin Password</label>
              <input
                type="password"
                placeholder="At least 6 characters"
                value={newAdminPass}
                onChange={e => setNewAdminPass(e.target.value)}
                onKeyDown={e => e.key === 'Enter' && handleResetPassword()}
              />
            </div>

            <button className="login-btn" onClick={handleResetPassword} disabled={loading}>
              {loading ? <span className="spinner" /> : 'Reset Password'}
            </button>

            <button 
              className="login-tab" 
              onClick={() => { setShowReset(false); setError(''); setSuccess('') }}
              style={{ width: '100%', border: 'none', background: 'none', cursor: 'pointer', marginTop: 14, color: 'var(--text-muted)', fontSize: 12 }}
            >
              ← Back to Admin Login
            </button>
          </>
        ) : (
          <>
            <div className="login-tabs">
              <button className={`login-tab ${tab === 'license' ? 'active' : ''}`} onClick={() => { setTab('license'); setError(''); setSuccess('') }} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <IconKey size={14} /> License Key
              </button>
              <button className={`login-tab ${tab === 'admin' ? 'active' : ''}`} onClick={() => { setTab('admin'); setError(''); setSuccess('') }} style={{ display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: 6 }}>
                <IconSettings size={14} /> Admin Login
              </button>
            </div>

            {error && <div className="login-error">{error}</div>}
            {success && <div className="login-success">{success}</div>}

            {tab === 'license' ? (
              <>
                <div className="login-field">
                  <label>License Key</label>
                  <input
                    type="text"
                    placeholder="SS-XXXX-XXXX-XXXX"
                    value={licenseKey}
                    onChange={e => setLicenseKey(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleLicenseLogin()}
                  />
                </div>
                <div className="login-field" style={{ marginTop: 12 }}>
                  <label>Gmail / Email</label>
                  <input
                    type="email"
                    placeholder="user@gmail.com"
                    value={userEmail}
                    onChange={e => setUserEmail(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleLicenseLogin()}
                  />
                </div>
                <button className="login-btn" onClick={handleLicenseLogin} disabled={loading} style={{ marginTop: 16 }}>
                  {loading ? <span className="spinner" /> : 'Verify & Login'}
                </button>

                <div className="login-divider">Don't have a license?</div>

                <a href={WHATSAPP_URL} target="_blank" rel="noopener noreferrer" className="whatsapp-login-btn" style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
                  <IconMessageSquare size={16} /> Contact Developer on WhatsApp
                </a>
              </>
            ) : (
              <>
                <div className="login-field">
                  <label>Admin Password</label>
                  <input
                    type="password"
                    placeholder="Enter admin password"
                    value={adminPass}
                    onChange={e => setAdminPass(e.target.value)}
                    onKeyDown={e => e.key === 'Enter' && handleAdminLogin()}
                  />
                </div>
                <button className="login-btn" onClick={handleAdminLogin} disabled={loading}>
                  {loading ? <span className="spinner" /> : 'Admin Login'}
                </button>

                <div style={{ textAlign: 'right', marginTop: 12 }}>
                  <button 
                    onClick={() => { setShowReset(true); setError(''); setSuccess('') }}
                    style={{ background: 'none', border: 'none', color: 'var(--accent-purple)', fontSize: 11, cursor: 'pointer', fontFamily: 'inherit', fontWeight: 600 }}
                  >
                    Forgot Password?
                  </button>
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
//  DASHBOARD PAGE
// ═══════════════════════════════════════════════════════════════════════
function DashboardPage({ session, adminSession }: { session: LicenseSession | null, adminSession: AdminSession | null }) {
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [scanResults, setScanResults] = useState<SignalResponse[]>([])
  const [scanning, setScanning] = useState(false)
  const [scanError, setScanError] = useState('')

  // Load admin stats if admin
  useEffect(() => {
    if (!adminSession) return
    fetch(`${API}/admin/dashboard-stats`, {
      headers: { 'x-admin-token': adminSession.token },
    })
      .then(r => r.json())
      .then(setStats)
      .catch(() => {})
  }, [adminSession])

  const handleQuickScan = async () => {
    setScanning(true); setScanError(''); setScanResults([])
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      let url = `${API}/admin/signal/scan-quotex?duration=1+Minute`
      if (adminSession) {
        headers['x-admin-token'] = adminSession.token
      } else if (session) {
        // Need API key for user scan — use admin scan if available
        url = `${API}/admin/signal/scan-quotex?duration=1+Minute`
        headers['x-admin-token'] = '' // will fail, but show error
      }
      const res = await fetch(url, { method: 'POST', headers })
      if (!res.ok) {
        const err = await res.json()
        setScanError(err.detail || 'Scan failed')
        setScanning(false)
        return
      }
      const data = await res.json()
      setScanResults(data)
    } catch {
      setScanError('Connection failed')
    }
    setScanning(false)
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Dashboard</h1>
        <p className="page-subtitle">
          {session ? `Welcome back, ${session.username}` : 'Admin Overview'}
          {session && <> · License expires {fmtDate(session.expires_at)}</>}
        </p>
      </div>

      {/* Stats Cards */}
      {stats && (
        <div className="stats-grid">
          <div className="stat-card purple">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-purple)' }}><IconUsers size={20} /></div>
              <span className="stat-card-label">Total Users</span>
            </div>
            <div className="stat-card-value">{stats.total_users}</div>
          </div>
          <div className="stat-card green">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-green)' }}><IconCheck size={18} /></div>
              <span className="stat-card-label">Active Users</span>
            </div>
            <div className="stat-card-value">{stats.active_users}</div>
          </div>
          <div className="stat-card red">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-red)' }}><IconHourglass size={18} /></div>
              <span className="stat-card-label">Expired Licenses</span>
            </div>
            <div className="stat-card-value">{stats.expired_licenses}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-blue)' }}><IconActivity size={18} /></div>
              <span className="stat-card-label">Online Now</span>
            </div>
            <div className="stat-card-value">{stats.online_users}</div>
          </div>
        </div>
      )}

      {/* Non-admin user stats */}
      {session && !adminSession && (
        <div className="stats-grid">
          <div className="stat-card purple">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-purple)' }}><IconKey size={18} /></div>
              <span className="stat-card-label">License</span>
            </div>
            <div className="stat-card-value" style={{ fontSize: 16, wordBreak: 'break-all' }}>{session.license_key}</div>
          </div>
          <div className="stat-card green">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-green)' }}><IconCalendar size={18} /></div>
              <span className="stat-card-label">Expires</span>
            </div>
            <div className="stat-card-value" style={{ fontSize: 18 }}>{fmtDate(session.expires_at)}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-blue)' }}><IconShield size={18} /></div>
              <span className="stat-card-label">Status</span>
            </div>
            <div className="stat-card-value" style={{ fontSize: 18, color: 'var(--accent-green)' }}>Active</div>
          </div>
          <div className="stat-card amber">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-amber)' }}><IconLock size={18} /></div>
              <span className="stat-card-label">Device Bound</span>
            </div>
            <div className="stat-card-value" style={{ fontSize: 14, wordBreak: 'break-all', color: 'var(--text-secondary)' }}>
              {session.device_id.slice(0, 16)}…
            </div>
          </div>
        </div>
      )}

      {/* Quick Scan Section */}
      <div style={{ marginBottom: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 16 }}>
          <h2 style={{ fontSize: 18, fontWeight: 700 }}>Quick Market Scan</h2>
          <span className="double-pass-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
            <IconDoubleCheck size={14} style={{ color: 'var(--accent-purple)' }} /> Double-Pass Analysis
          </span>
        </div>
        {adminSession && (
          <button className="btn-scan" onClick={handleQuickScan} disabled={scanning} style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
            {scanning ? (
              <>
                <span className="spinner" /> Scanning all Quotex OTC pairs…
              </>
            ) : (
              <>
                <IconActivity size={16} /> Scan All Quotex OTC Pairs
              </>
            )}
          </button>
        )}
        {!adminSession && (
          <p style={{ color: 'var(--text-muted)', fontSize: 13 }}>
            Use the <strong>Generate Signal</strong> page to analyze individual pairs.
          </p>
        )}
      </div>

      {scanError && <div className="login-error" style={{ maxWidth: 500 }}>{scanError}</div>}

      {/* Scan Results */}
      {scanResults.length > 0 && (
        <div className="scan-results">
          <table className="scan-table">
            <thead>
              <tr>
                <th>Pair</th>
                <th>Signal</th>
                <th>Confidence</th>
                <th>Trend</th>
                <th>Price</th>
              </tr>
            </thead>
            <tbody>
              {scanResults.map((r, i) => (
                <tr key={i}>
                  <td style={{ fontWeight: 600 }}>{r.pair}</td>
                  <td>
                    <span className={`mini-badge ${r.signal.toLowerCase()}`} style={{ display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                      {r.signal === 'UP' ? (
                        <>
                          <IconTrendUp size={11} /> BUY
                        </>
                      ) : r.signal === 'DOWN' ? (
                        <>
                          <IconTrendDown size={11} /> SELL
                        </>
                      ) : (
                        <>
                          <IconHourglass size={11} /> WAIT
                        </>
                      )}
                    </span>
                  </td>
                  <td>
                    <span style={{ fontWeight: 700, color: r.confidence >= 75 ? 'var(--accent-green)' : r.confidence >= 50 ? 'var(--accent-amber)' : 'var(--accent-red)' }}>
                      {r.confidence}%
                    </span>
                  </td>
                  <td style={{ color: 'var(--text-secondary)' }}>{r.market_trend}</td>
                  <td style={{ fontFamily: 'monospace' }}>{r.current_price.toFixed(5)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


// ─── Inline SVG Icons (Professional Vector Icons) ──────────────────────
function IconCheck({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 6 9 17l-5-5"/>
    </svg>
  )
}

function IconDoubleCheck({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M17 5 9.5 12.5 7 10" />
      <path d="m22 5-7.5 7.5" />
      <path d="m2 12.5 5 5 1.5-1.5" />
    </svg>
  )
}

function IconTrendUp({ className = '', size = 24, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
      <polyline points="16 7 22 7 22 13" />
    </svg>
  )
}

function IconTrendDown({ className = '', size = 24, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 17 13.5 8.5 8.5 13.5 2 7" />
      <polyline points="16 17 22 17 22 11" />
    </svg>
  )
}

function IconHourglass({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M5 2h14" />
      <path d="M5 22h14" />
      <path d="M19 2v4c0 1.38-1.13 2.5-2.5 2.5S14 7.38 14 6V2" />
      <path d="M14 22v-4c0-1.38 1.13-2.5 2.5-2.5s2.5 1.12 2.5 2.5v4" />
      <path d="M5 2v4c0 1.38 1.13 2.5 2.5 2.5S10 7.38 10 6V2" />
      <path d="M10 22v-4c0-1.38-1.13-2.5-2.5-2.5S5 16.62 5 18v4" />
    </svg>
  )
}

function IconAlertTriangle({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
      <line x1="12" y1="9" x2="12" y2="13" />
      <line x1="12" y1="17" x2="12.01" y2="17" />
    </svg>
  )
}

function IconChart({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <line x1="18" y1="20" x2="18" y2="10" />
      <line x1="12" y1="20" x2="12" y2="4" />
      <line x1="6" y1="20" x2="6" y2="14" />
    </svg>
  )
}

function IconGlobe({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="10" />
      <line x1="2" y1="12" x2="22" y2="12" />
      <path d="M12 2a15.3 15.3 0 0 1 4 10 15.3 15.3 0 0 1-4 10 15.3 15.3 0 0 1-4-10 15.3 15.3 0 0 1 4-10z" />
    </svg>
  )
}

function IconCoins({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="8" cy="8" r="6" />
      <circle cx="18" cy="18" r="4" />
      <path d="M12 18a6 6 0 0 0-6-6" />
    </svg>
  )
}

function IconActivity({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round">
      <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
    </svg>
  )
}

function IconHome({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m3 9 9-7 9 7v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z" />
      <polyline points="9 22 9 12 15 12 15 22" />
    </svg>
  )
}

function IconClipboard({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="8" y="2" width="8" height="4" rx="1" ry="1" />
      <path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2" />
    </svg>
  )
}

function IconFlask({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M6 3h12" />
      <path d="M12 3v12" />
      <path d="M18 15V3" />
      <path d="M6 15V3" />
      <path d="M3 21h18" />
      <path d="M12 21a6 6 0 0 1-6-6v0h12v0a6 6 0 0 1-6 6Z" />
    </svg>
  )
}

function IconSettings({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

function IconLogout({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1-2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

function IconUsers({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
      <circle cx="9" cy="7" r="4" />
      <path d="M22 21v-2a4 4 0 0 0-3-3.87" />
      <path d="M16 3.13a4 4 0 0 1 0 7.75" />
    </svg>
  )
}

function IconKey({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="m21 2-2 2m-7.61 7.61a5.5 5.5 0 1 1-7.778 7.778 5.5 5.5 0 0 1 7.777-7.777zm0 0L15.5 7.5m0 0 3 3L22 7l-3-3m-3.5 3.5L19 4" />
    </svg>
  )
}

function IconCalendar({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
      <line x1="16" y1="2" x2="16" y2="6" />
      <line x1="8" y1="2" x2="8" y2="6" />
      <line x1="3" y1="10" x2="21" y2="10" />
    </svg>
  )
}

function IconShield({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 4 8 10z" />
    </svg>
  )
}

function IconLock({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="11" width="18" height="11" rx="2" ry="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  )
}

function IconMessageSquare({ className = '', size = 16, style = {} }: { className?: string; size?: number; style?: React.CSSProperties }) {
  return (
    <svg className={className} style={style} width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
    </svg>
  )
}


// ═══════════════════════════════════════════════════════════════════════
//  DEEP ANALYSIS LOADER
// ═══════════════════════════════════════════════════════════════════════
const ANALYSIS_STEPS = [
  { label: 'Fetching live market data…',               ms: 1500 },
  { label: 'Computing 11 technical indicators…',       ms: 800  },
  { label: 'ADX + EMA + RSI analysis…',                ms: 600  },
  { label: 'Finalizing signal decision…',              ms: 400  },
]

function DeepLoader() {
  const [step, setStep] = useState(0)
  const [elapsed, setElapsed] = useState(0)

  useEffect(() => {
    const timers: ReturnType<typeof setTimeout>[] = []
    let acc = 0
    ANALYSIS_STEPS.forEach((s, i) => {
      timers.push(setTimeout(() => setStep(i), acc))
      acc += s.ms
    })
    const ticker = setInterval(() => setElapsed(e => e + 100), 100)
    return () => { timers.forEach(clearTimeout); clearInterval(ticker) }
  }, [])

  const totalMs = ANALYSIS_STEPS.reduce((s, x) => s + x.ms, 0)
  const progress = Math.min(99, Math.round(elapsed / totalMs * 100))

  return (
    <div style={{
      margin: '28px 0', padding: '28px 32px',
      background: 'linear-gradient(135deg, rgba(109,40,217,0.10), rgba(30,20,60,0.85))',
      border: '1px solid rgba(139,92,246,0.25)', borderRadius: 18,
      boxShadow: '0 8px 40px rgba(109,40,217,0.15)',
    }}>
      {/* Header */}
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 22 }}>
        <div style={{
          width: 40, height: 40, borderRadius: '50%',
          background: 'linear-gradient(135deg,#7c3aed,#4f46e5)',
          display: 'flex', alignItems: 'center', justifyContent: 'center',
          flexShrink: 0,
          boxShadow: '0 0 18px rgba(124,58,237,0.5)',
          animation: 'spin 4s linear infinite',
          color: 'white',
        }}>
          <IconActivity size={20} />
        </div>
        <div>
          <div style={{ fontWeight: 800, fontSize: 16, color: '#e2d9f3' }}>Deep Market Analysis</div>
          <div style={{ fontSize: 12, color: 'rgba(196,181,253,0.7)', marginTop: 2 }}>Multi-indicator · 11 signals · Double-pass confirmed</div>
        </div>
      </div>

      {/* Steps */}
      <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginBottom: 22 }}>
        {ANALYSIS_STEPS.map((s, i) => {
          const done = i < step
          const active = i === step
          return (
            <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 10,
              opacity: i > step ? 0.35 : 1,
              transition: 'opacity 0.4s ease' }}>
              <div style={{
                width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                fontSize: 11, fontWeight: 800,
                background: done ? 'rgba(16,185,129,0.2)' : active ? 'rgba(139,92,246,0.25)' : 'rgba(255,255,255,0.05)',
                border: `1.5px solid ${done ? '#10b981' : active ? '#8b5cf6' : 'rgba(255,255,255,0.1)'}`,
                color: done ? '#10b981' : active ? '#c4b5fd' : '#6b7280',
                transition: 'all 0.4s ease',
                animation: active ? 'pulse 1.2s ease-in-out infinite' : 'none',
              }}>
                {done ? <IconCheck size={10} /> : i + 1}
              </div>
              <span style={{
                fontSize: 13, fontWeight: active ? 600 : 400,
                color: done ? '#10b981' : active ? '#e2d9f3' : '#6b7280',
                transition: 'color 0.4s ease',
              }}>{s.label}</span>
              {active && <div style={{
                marginLeft: 'auto', display: 'flex', gap: 3,
              }}>
                {[0,1,2].map(d => (
                  <div key={d} style={{
                    width: 5, height: 5, borderRadius: '50%',
                    background: '#8b5cf6',
                    animation: `bounce 0.9s ${d*0.2}s ease-in-out infinite`,
                  }} />
                ))}
              </div>}
            </div>
          )
        })}
      </div>

      {/* Progress bar */}
      <div style={{ background: 'rgba(255,255,255,0.06)', borderRadius: 8, height: 7, overflow: 'hidden' }}>
        <div style={{
          height: '100%', borderRadius: 8,
          background: 'linear-gradient(90deg, #7c3aed, #4f46e5, #06b6d4)',
          width: `${progress}%`,
          transition: 'width 0.3s ease',
          boxShadow: '0 0 10px rgba(124,58,237,0.6)',
        }} />
      </div>
      <div style={{ textAlign: 'right', fontSize: 11, color: 'rgba(196,181,253,0.6)', marginTop: 6 }}>
        {progress}% · {(elapsed / 1000).toFixed(1)}s elapsed
      </div>
    </div>
  )
}

// ═══════════════════════════════════════════════════════════════════════
//  SIGNALS PAGE (Generate Signal)
// ═══════════════════════════════════════════════════════════════════════
function SignalsPage({ session, adminSession }: { session: LicenseSession | null, adminSession: AdminSession | null }) {
  const [marketType, setMarketType] = useState<MarketTab>('quotex')
  const [pair, setPair] = useState(QUOTEX_PAIRS[0])
  const [duration, setDuration] = useState('1 Minute')
  const [generating, setGenerating] = useState(false)
  const [result, setResult] = useState<SignalResponse | null>(null)
  const [error, setError] = useState('')

  // ── Best Pair Finder state ──────────────────────────────────────────
  const [finding, setFinding] = useState(false)
  const [bestPairResult, setBestPairResult] = useState<SignalResponse | null>(null)
  const [bestPairError, setBestPairError] = useState('')
  const [scanProgress, setScanProgress] = useState('')
  const [scanAllResults, setScanAllResults] = useState<SignalResponse[]>([])

  const getMode = (t: MarketTab) => {
    if (t === 'quotex') return 'Quotex'
    if (t === 'forex') return 'Forex'
    return 'Crypto'
  }

  const handleGenerate = async () => {
    setGenerating(true); setError(''); setResult(null)
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      let url: string
      if (adminSession) {
        url = `${API}/admin/signal/generate`
        headers['x-admin-token'] = adminSession.token
      } else {
        url = `${API}/signals/generate`
        if (session) headers['x-user-token'] = session.token
      }
      const res = await fetch(url, {
        method: 'POST',
        headers,
        body: JSON.stringify({ mode: getMode(marketType), pair, duration }),
      })
      if (!res.ok) {
        const err = await res.json()
        const detail = err.detail || 'Signal generation failed'
        const lowerDetail = detail.toLowerCase()
        if (lowerDetail.includes('closed') || lowerDetail.includes('weekend') || lowerDetail.includes('after-hours')) {
          setError('🔴 Market Closed — Forex market is closed on weekends. Switch to an OTC pair (shown with "OTC" in name) — they work 24/7!')
        } else {
          setError(detail)
        }
        setGenerating(false)
        return
      }
      const data = await res.json()
      setResult(data)
    } catch {
      setError('Connection failed. Make sure the backend is running.')
    }
    setGenerating(false)
  }

  const handleMarketTypeChange = (t: MarketTab) => {
    setMarketType(t)
    setBestPairResult(null)
    setBestPairError('')
    setScanAllResults([])
    if (t === 'quotex') setPair(QUOTEX_PAIRS[0])
    else if (t === 'forex') setPair(FOREX_PAIRS[0])
    else setPair(CRYPTO_PAIRS[0])
  }

  // ── Best Pair Finder — scans all pairs & picks highest confidence signal ──
  const handleFindBestPair = async () => {
    setFinding(true); setBestPairError(''); setBestPairResult(null); setScanAllResults([]); setResult(null); setError('')
    const mode = getMode(marketType)
    const headers: Record<string, string> = { 'Content-Type': 'application/json' }

    // Choose the correct scan endpoint
    let scanUrl = ''
    if (adminSession) {
      headers['x-admin-token'] = adminSession.token
      if (marketType === 'quotex') {
        scanUrl = `${API}/admin/signal/scan-quotex?duration=${encodeURIComponent(duration)}`
      } else {
        scanUrl = `${API}/admin/signal/scan?mode=${mode}&duration=${encodeURIComponent(duration)}`
      }
    } else if (session) {
      headers['x-user-token'] = session.token
      if (marketType === 'quotex') {
        scanUrl = `${API}/signals/scan-quotex?duration=${encodeURIComponent(duration)}`
      } else {
        scanUrl = `${API}/signals/scan?mode=${mode}&duration=${encodeURIComponent(duration)}`
      }
    } else {
      setBestPairError('Login required to scan pairs.')
      setFinding(false)
      return
    }

    try {
      setScanProgress(
        marketType === 'quotex'
          ? `Scanning ${QUOTEX_PAIRS.length} Quotex pairs (OTC + Live)…`
          : marketType === 'forex'
          ? `Scanning ${FOREX_PAIRS.length} Forex pairs…`
          : `Scanning ${CRYPTO_PAIRS.length} Crypto pairs…`
      )
      const res = await fetch(scanUrl, { method: 'POST', headers })
      if (!res.ok) {
        const err = await res.json()
        setBestPairError(err.detail || 'Scan failed. Try again.')
        setFinding(false)
        return
      }
      const allResults: SignalResponse[] = await res.json()
      // Filter UP/DOWN signals from Chinese Bot
      const actionable = allResults
        .filter(r => r.signal !== 'WAIT' && r.status !== 'MARKET_CLOSED')
        .sort((a, b) => b.confidence - a.confidence)

      // Store top 5 results for leaderboard display
      setScanAllResults(actionable.slice(0, 5))

      if (actionable.length === 0) {
        // No strong signal — show best available
        const bestWait = [...allResults].sort((a, b) => b.confidence - a.confidence)[0]
        if (bestWait) {
          setBestPairResult({ ...bestWait, signal: 'WAIT' })
          setBestPairError('⏳ No strong signal right now — market is sideways. Wait a few minutes and scan again.')
        } else {
          setBestPairError('No results from backend. Check connection.')
        }
      } else {
        const best = actionable[0]
        setBestPairResult(best)
        // Auto-select this pair in the dropdown
        setPair(best.pair)
      }
    } catch {
      setBestPairError('Connection failed. Is the backend running?')
    }
    setScanProgress('')
    setFinding(false)
  }

  const activePairs =
    marketType === 'quotex' ? QUOTEX_PAIRS :
    marketType === 'forex'  ? FOREX_PAIRS  : CRYPTO_PAIRS

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Generate Signal</h1>
        <p className="page-subtitle">Deep market analysis · 11 indicators · Ultra-accurate signals</p>
      </div>

      {/* Market Type Tab */}
      <div className="market-type-tabs">
        <button className="market-tab active"
          style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <IconChart size={15} /> Trading Bot
        </button>
      </div>

      {/* ── Polished Signal Setup Card ───────────────────────────────────── */}
      <div className="signal-controls-card">
        <div className="signal-controls-header">
          <div className="signal-controls-title">
            <IconActivity size={18} color="#8b5cf6" /> Setup Signal Request
          </div>
          <div className="signal-controls-badge">Quotex AI Engine Active</div>
        </div>

        <div className="signal-controls">
          <div className="control-group">
            <span className="control-label">TRADING PAIR</span>
            <CustomDropdown
              options={activePairs}
              value={pair}
              onChange={setPair}
              searchable={true}
            />
          </div>
          <div className="control-group">
            <span className="control-label">DURATION</span>
            <CustomDropdown
              options={DURATIONS}
              value={duration}
              onChange={setDuration}
              searchable={false}
            />
          </div>
          <button className="btn-generate" onClick={handleGenerate} disabled={generating}>
            {generating ? (
              <>
                <span className="spinner" /> Analyzing…
              </>
            ) : (
              <>
                <IconActivity size={18} /> Analyze
              </>
            )}
          </button>
        </div>
      </div>

      {error && <div className="login-error" style={{ maxWidth: 520, marginTop: 16 }}>{error}</div>}

      {generating && <DeepLoader />}

      {result && <SignalCard result={result} />}
    </div>
  )
}

// ─── Signal Result Card ────────────────────────────────────────────────
function SignalCard({ result }: { result: SignalResponse }) {
  const [showDetails, setShowDetails] = useState(false)
  // Apply the 65% confidence threshold: below 65% always shows as WAIT
  const effectiveSig: Signal = result.confidence >= MIN_CONFIDENCE ? result.signal : 'WAIT'
  const sig = effectiveSig
  const belowThreshold = result.confidence < MIN_CONFIDENCE

  const confClass = (score: number) => {
    if (score >= 75) return 'conf-high'
    if (score >= 60) return 'conf-medium'
    return 'conf-low'
  }

  return (
    <div className="signal-result" style={{ position: 'relative', overflow: 'hidden' }}>
      
      {/* Header Info */}
      <div className="signal-header" style={{ marginBottom: 20 }}>
        <div>
          <div className="signal-pair-name" style={{ fontSize: 24, fontWeight: 900, color: 'var(--text-primary)' }}>{result.pair}</div>
          <span className="double-pass-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: 6, marginTop: 4 }}>
            <IconDoubleCheck size={14} style={{ color: 'var(--accent-purple)' }} /> Double-Pass Confirmed
          </span>
        </div>
      </div>

      {/* BIG CALL-TO-ACTION TRADER DISPLAY */}
      {sig === 'UP' && (
        <div style={{
          margin: '0 0 24px 0', padding: '24px',
          background: 'linear-gradient(135deg, rgba(16,185,129,0.12), rgba(16,185,129,0.02))',
          border: '1px solid rgba(16,185,129,0.3)',
          borderRadius: '16px',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 20,
          boxShadow: '0 8px 30px rgba(16,185,129,0.08)',
        }}>
          <div style={{
            width: 60, height: 60, borderRadius: '50%',
            background: 'rgba(16,185,129,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--accent-green)', flexShrink: 0,
            boxShadow: '0 0 20px rgba(16,185,129,0.2)',
          }}>
            <IconTrendUp size={36} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--accent-green)', textTransform: 'uppercase', letterSpacing: 1 }}>TRADER INSTRUCTION</div>
            <div style={{ fontSize: 26, fontWeight: 900, color: 'var(--accent-green)', marginTop: 2, letterSpacing: -0.5 }}>STRONG BUY / CALL 📈</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 3 }}>Market shows strong bullish pressure. Enter UP trade.</div>
          </div>
        </div>
      )}

      {sig === 'DOWN' && (
        <div style={{
          margin: '0 0 24px 0', padding: '24px',
          background: 'linear-gradient(135deg, rgba(244,63,94,0.12), rgba(244,63,94,0.02))',
          border: '1px solid rgba(244,63,94,0.3)',
          borderRadius: '16px',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 20,
          boxShadow: '0 8px 30px rgba(244,63,94,0.08)',
        }}>
          <div style={{
            width: 60, height: 60, borderRadius: '50%',
            background: 'rgba(244,63,94,0.15)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--accent-red)', flexShrink: 0,
            boxShadow: '0 0 20px rgba(244,63,94,0.2)',
          }}>
            <IconTrendDown size={36} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--accent-red)', textTransform: 'uppercase', letterSpacing: 1 }}>TRADER INSTRUCTION</div>
            <div style={{ fontSize: 26, fontWeight: 900, color: 'var(--accent-red)', marginTop: 2, letterSpacing: -0.5 }}>STRONG SELL / PUT 📉</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 3 }}>Market shows heavy bearish pressure. Enter DOWN trade.</div>
          </div>
        </div>
      )}

      {sig === 'WAIT' && (
        <div style={{
          margin: '0 0 24px 0', padding: '24px',
          background: 'linear-gradient(135deg, rgba(251,191,36,0.08), rgba(251,191,36,0.02))',
          border: '1px solid rgba(251,191,36,0.25)',
          borderRadius: '16px',
          display: 'flex',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 20,
          boxShadow: '0 8px 30px rgba(251,191,36,0.05)',
        }}>
          <div style={{
            width: 60, height: 60, borderRadius: '50%',
            background: 'rgba(251,191,36,0.12)',
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            color: 'var(--accent-amber)', flexShrink: 0,
          }}>
            <IconHourglass size={30} />
          </div>
          <div>
            <div style={{ fontSize: 13, fontWeight: 800, color: 'var(--accent-amber)', textTransform: 'uppercase', letterSpacing: 1 }}>TRADER INSTRUCTION</div>
            <div style={{ fontSize: 22, fontWeight: 900, color: 'var(--accent-amber)', marginTop: 2, letterSpacing: -0.5 }}>WAIT / NO TRADE ⏳</div>
            <div style={{ fontSize: 13, color: 'var(--text-secondary)', marginTop: 3 }}>Confluence is low or directions conflict. Abort entry.</div>
          </div>
        </div>
      )}

      {belowThreshold && (
        <div className="confidence-threshold-warning" style={{ display: 'flex', alignItems: 'flex-start', gap: 10, margin: '0 0 24px 0' }}>
          <IconAlertTriangle size={18} style={{ flexShrink: 0, color: 'var(--accent-amber)', marginTop: 2 }} />
          <div>
            Confidence {result.confidence}% is below the 65% safety threshold. Waiting for a stronger direction before recommending a real entry.
          </div>
        </div>
      )}

      {/* Grid details */}
      <div className="signal-meta">
        <div className="signal-meta-item">
          <div className="signal-meta-label">Price</div>
          <div className="signal-meta-value" style={{ fontFamily: 'monospace' }}>{result.current_price.toFixed(5)}</div>
        </div>
        <div className="signal-meta-item">
          <div className="signal-meta-label">Confidence</div>
          <div className="signal-meta-value" style={{ color: result.confidence >= 75 ? 'var(--accent-green)' : result.confidence >= 58 ? 'var(--accent-amber)' : 'var(--accent-red)' }}>
            {result.confidence}%
          </div>
        </div>
        <div className="signal-meta-item">
          <div className="signal-meta-label">Duration</div>
          <div className="signal-meta-value">{result.duration}</div>
        </div>
        <div className="signal-meta-item">
          <div className="signal-meta-label">Trend</div>
          <div className="signal-meta-value">{result.market_trend}</div>
        </div>
      </div>

      <div className="signal-confidence-bar" style={{ marginBottom: 20 }}>
        <div className={`signal-confidence-fill ${confClass(result.confidence)}`} style={{ width: `${result.confidence}%` }} />
      </div>

      {result.analysis && result.analysis.length > 0 && (
        <div className="signal-analysis">
          <button 
            onClick={() => setShowDetails(!showDetails)}
            style={{
              background: 'rgba(255,255,255,0.02)',
              border: '1px solid rgba(255,255,255,0.05)',
              width: '100%',
              display: 'flex', alignItems: 'center', justifyContent: 'space-between',
              padding: '12px 16px', borderRadius: 10,
              color: 'var(--text-secondary)', fontWeight: 700, fontSize: 13,
              cursor: 'pointer', fontFamily: 'inherit', outline: 'none',
              transition: 'var(--transition)'
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}>
              <IconClipboard size={14} style={{ color: 'var(--accent-purple)' }} /> Confluence Details
            </span>
            <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
              {showDetails ? 'Hide Details ▲' : 'Show Details ▼'}
            </span>
          </button>

          {showDetails && (
            <div className="signal-analysis-list" style={{ marginTop: 12, animation: 'fadeIn 0.3s ease' }}>
              {result.analysis.map((a, i) => (
                <div className="signal-analysis-item" key={i} style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                  {a.trim().startsWith('🟢') ? (
                    <IconCheck size={11} style={{ color: 'var(--accent-green)', flexShrink: 0 }} />
                  ) : a.trim().startsWith('🔴') ? (
                    <svg width="10" height="10" viewBox="0 0 10 10" fill="none" style={{ flexShrink: 0, color: 'var(--accent-red)' }}>
                      <path d="M1 9L9 1M1 1L9 9" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" />
                    </svg>
                  ) : (
                    <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'rgba(255,255,255,0.2)', flexShrink: 0 }} />
                  )}
                  <span>{a.replace(/^[🟢🔴⚪]/, '').trim()}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

      {result.data_warning && (
        <div style={{ marginTop: 14, padding: '10px 14px', background: 'rgba(251,191,36,0.06)', border: '1px solid rgba(251,191,36,0.15)', borderRadius: 10, fontSize: 12, color: 'var(--accent-amber)', display: 'flex', alignItems: 'center', gap: 8 }}>
          <IconAlertTriangle size={14} style={{ flexShrink: 0 }} />
          <span>{result.data_warning}</span>
        </div>
      )}
    </div>
  )
}



// ═══════════════════════════════════════════════════════════════════════
//  HISTORY PAGE
// ═══════════════════════════════════════════════════════════════════════
function HistoryPage({ session, adminSession }: { session: LicenseSession | null, adminSession: AdminSession | null }) {
  const [history, setHistory] = useState<HistoryRow[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    const loadHistory = async () => {
      setLoading(true)
      try {
        if (adminSession) {
          // Admin: view user 1 history
          const res = await fetch(`${API}/admin/users/1/history?limit=100`, {
            headers: { 'x-admin-token': adminSession.token },
          })
          if (res.ok) setHistory(await res.json())
        }
      } catch { /* ignore */ }
      setLoading(false)
    }
    loadHistory()
  }, [session, adminSession])

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Trade History</h1>
        <p className="page-subtitle">Record of all generated signals</p>
      </div>

      {loading ? (
        <div className="loading-overlay">
          <div className="spinner" style={{ width: 32, height: 32 }} />
          <div className="loading-text">Loading history…</div>
        </div>
      ) : history.length === 0 ? (
        <div className="empty-state">
          <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)', marginBottom: 12 }}>
            <IconClipboard size={44} />
          </div>
          <div className="empty-state-text">No trade history yet. Generate some signals first!</div>
        </div>
      ) : (
        <div className="scan-results">
          <table className="scan-table">
            <thead>
              <tr>
                <th>#</th>
                <th>Date</th>
                <th>Pair</th>
                <th>Signal</th>
                <th>Confidence</th>
                <th>Duration</th>
                <th>Trend</th>
                <th>Outcome</th>
              </tr>
            </thead>
            <tbody>
              {history.map(h => (
                <tr key={h.id}>
                  <td>{h.id}</td>
                  <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{fmtDate(h.created_at)}</td>
                  <td style={{ fontWeight: 600 }}>{h.pair}</td>
                  <td><span className={`mini-badge ${h.signal.toLowerCase()}`}>{h.signal}</span></td>
                  <td style={{ fontWeight: 600 }}>{h.confidence}%</td>
                  <td>{h.duration}</td>
                  <td style={{ color: 'var(--text-secondary)' }}>{h.market_trend}</td>
                  <td>
                    {h.outcome
                      ? <span className={`mini-badge ${h.outcome === 'WIN' ? 'up' : h.outcome === 'LOSS' ? 'down' : 'wait'}`}>{h.outcome}</span>
                      : <span style={{ color: 'var(--text-muted)' }}>—</span>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════════
//  BACKTEST PAGE — 10 simulated trades per pair
// ═══════════════════════════════════════════════════════════════════════
interface BacktestResult {
  pair: string; trades: number; wins: number; losses: number; winRate: number
  marketClosed?: boolean
  signals: Array<{ signal: string; confidence: number; win: boolean }>
}

function BacktestPage({ adminSession }: { adminSession: AdminSession | null }) {
  const [running, setRunning] = useState(false)
  const [results, setResults] = useState<BacktestResult[]>([])
  const [progress, setProgress] = useState({ current: 0, total: 0, currentPair: '' })
  const [marketType, setMarketType] = useState<'otc' | 'live' | 'all' | 'forex'>('otc')

  const getPairs = () => {
    if (marketType === 'otc') return QUOTEX_OTC
    if (marketType === 'live') return QUOTEX_LIVE
    if (marketType === 'forex') return FOREX_PAIRS.slice(0, 20)  // top 20 forex pairs
    return ALL_QUOTEX
  }

  const getMode = () => {
    if (marketType === 'forex') return 'Forex'
    return 'Quotex'
  }

  const simulateOneTrade = async (pair: string, mode: string) => {
    try {
      const headers: Record<string, string> = { 'Content-Type': 'application/json' }
      // Use admin endpoint if available, otherwise open endpoint
      let url: string
      if (adminSession) {
        url = `${API}/admin/signal/generate`
        headers['x-admin-token'] = adminSession.token
      } else {
        url = `${API}/signals/generate`
      }
      const res = await fetch(url, {
        method: 'POST', headers,
        body: JSON.stringify({ mode, pair, duration: '1 Minute' }),
      })
      if (!res.ok) {
        const errData = await res.json().catch(() => ({}))
        const errMsg = (errData?.detail || '').toLowerCase()
        if (errMsg.includes('closed') || errMsg.includes('weekend') || errMsg.includes('after-hours')) {
          return { signal: 'WAIT', confidence: 0, win: false, marketClosed: true }
        }
        return { signal: 'WAIT', confidence: 0, win: false, marketClosed: false }
      }
      const data = await res.json()
      // Check if market_closed status returned
      if (data.status === 'MARKET_CLOSED') {
        return { signal: 'WAIT', confidence: 0, win: false, marketClosed: true }
      }
      // A trade is a WIN if signal is UP or DOWN with >= 65% confidence (not WAIT)
      const win = data.signal !== 'WAIT' && data.confidence >= MIN_CONFIDENCE
      return { signal: data.signal, confidence: data.confidence, win, marketClosed: false }
    } catch { return { signal: 'WAIT', confidence: 0, win: false, marketClosed: false } }
  }

  const runBacktest = async () => {
    setRunning(true); setResults([])
    const pairs = getPairs()
    const mode = getMode()
    setProgress({ current: 0, total: pairs.length, currentPair: '' })
    const allResults: BacktestResult[] = []

    for (let i = 0; i < pairs.length; i++) {
      const pair = pairs[i]
      setProgress({ current: i + 1, total: pairs.length, currentPair: pair })
      const trades: Array<{ signal: string; confidence: number; win: boolean; marketClosed?: boolean }> = []

      // First probe: check if market is closed for this pair
      const probeResult = await simulateOneTrade(pair, mode)
      if ((probeResult as any).marketClosed) {
        // Market is closed for this pair — skip trades, mark as closed
        allResults.push({
          pair, trades: 0, wins: 0, losses: 0, winRate: 0,
          marketClosed: true,
          signals: [],
        })
        setResults([...allResults])
        continue
      }
      trades.push(probeResult)

      // Collect remaining 9 trades (10 total)
      for (let t = 1; t < 10; t++) {
        const r = await simulateOneTrade(pair, mode)
        trades.push(r)
        await new Promise(res => setTimeout(res, 200))
      }

      const wins = trades.filter(t => t.win).length
      allResults.push({
        pair, trades: trades.length, wins,
        losses: trades.length - wins,
        winRate: Math.round((wins / trades.length) * 100),
        marketClosed: false,
        signals: trades,
      })
      setResults([...allResults])
    }
    setRunning(false)
  }

  const totalTrades = results.filter(r => !r.marketClosed).reduce((s, r) => s + r.trades, 0)
  const totalWins = results.filter(r => !r.marketClosed).reduce((s, r) => s + r.wins, 0)
  const overallWR = totalTrades ? Math.round((totalWins / totalTrades) * 100) : 0
  const closedCount = results.filter(r => r.marketClosed).length

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title" style={{ display: 'inline-flex', alignItems: 'center', gap: 10 }}>
          <IconFlask size={28} style={{ color: 'var(--accent-purple)' }} /> Backtest — 10 Trades Per Pair
        </h1>
        <p className="page-subtitle">Live AI analysis · 65%+ confidence trades only · Results shown in real-time</p>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
        <div className="market-type-tabs" style={{ margin: 0 }}>
          <button className={`market-tab ${marketType === 'otc' ? 'active' : ''}`} onClick={() => setMarketType('otc')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><IconHourglass size={13} /> OTC Only</button>
          <button className={`market-tab ${marketType === 'live' ? 'active' : ''}`} onClick={() => setMarketType('live')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><IconChart size={13} /> Live Only</button>
          <button className={`market-tab ${marketType === 'all' ? 'active' : ''}`} onClick={() => setMarketType('all')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><IconGlobe size={13} /> All Quotex</button>
          <button className={`market-tab ${marketType === 'forex' ? 'active' : ''}`} onClick={() => setMarketType('forex')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><IconCoins size={13} /> Forex/Metals</button>
        </div>
        <button className="btn-generate" onClick={runBacktest} disabled={running} style={{ margin: 0, display: 'inline-flex', alignItems: 'center', gap: 8 }}>
          {running ? <><span className="spinner" /> Analyzing {progress.current}/{progress.total}…</> : <><IconActivity size={16} /> Run 10 Trades / Pair</>}
        </button>

      </div>

      {running && progress.currentPair && (
        <div style={{ background: 'rgba(124,58,237,0.08)', border: '1px solid rgba(124,58,237,0.2)', borderRadius: 10, padding: '12px 16px', marginBottom: 20, display: 'flex', alignItems: 'center', gap: 12 }}>
          <span className="spinner" style={{ width: 18, height: 18 }} />
          <div>
            <div style={{ fontWeight: 600, fontSize: 14 }}>Analyzing: <span style={{ color: 'var(--accent-purple)' }}>{progress.currentPair}</span></div>
            <div style={{ fontSize: 12, color: 'var(--text-muted)' }}>Pair {progress.current} of {progress.total}</div>
          </div>
          <div style={{ marginLeft: 'auto', fontWeight: 800, fontSize: 18, color: 'var(--accent-purple)' }}>{Math.round((progress.current / progress.total) * 100)}%</div>
        </div>
      )}

      {results.length > 0 && (
        <div className="stats-grid" style={{ marginBottom: 24 }}>
          <div className="stat-card green">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-green)' }}><IconCheck size={18} /></div>
              <span className="stat-card-label">Overall Win Rate</span>
            </div>
            <div className="stat-card-value" style={{ color: overallWR >= 75 ? 'var(--accent-green)' : overallWR >= 60 ? 'var(--accent-amber)' : 'var(--accent-red)' }}>{overallWR}%</div>
          </div>
          <div className="stat-card purple">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-purple)' }}><IconChart size={18} /></div>
              <span className="stat-card-label">Pairs Tested</span>
            </div>
            <div className="stat-card-value">{results.filter(r => !r.marketClosed).length}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-blue)' }}><IconActivity size={18} /></div>
              <span className="stat-card-label">Total Trades</span>
            </div>
            <div className="stat-card-value">{totalTrades}</div>
          </div>
          <div className="stat-card amber">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-amber)' }}><IconDoubleCheck size={18} /></div>
              <span className="stat-card-label">Total Wins</span>
            </div>
            <div className="stat-card-value" style={{ color: 'var(--accent-green)' }}>{totalWins}</div>
          </div>
          {closedCount > 0 && (
            <div className="stat-card red">
              <div className="stat-card-header">
                <div className="stat-card-icon" style={{ color: 'var(--accent-red)' }}><IconAlertTriangle size={18} /></div>
                <span className="stat-card-label">Market Closed</span>
              </div>
              <div className="stat-card-value">{closedCount} pairs</div>
            </div>
          )}
        </div>
      )}

      {results.length > 0 && (
        <div className="scan-results">
          <table className="scan-table">
            <thead>
              <tr><th>Pair</th><th>Status</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win Rate</th><th>Trade Dots</th></tr>
            </thead>
            <tbody>
              {results.map((r, i) => (
                <tr key={i} style={r.marketClosed ? { opacity: 0.55 } : {}}>
                  <td style={{ fontWeight: 700 }}>{r.pair}</td>
                  <td>
                    {r.marketClosed
                      ? <span style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(239,68,68,0.12)', color: '#ef4444', borderRadius: 50, fontWeight: 700, whiteSpace: 'nowrap' }}>Market Closed</span>
                      : <span style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(16,185,129,0.12)', color: 'var(--accent-green)', borderRadius: 50, fontWeight: 700 }}>Live</span>
                    }
                  </td>
                  <td>{r.marketClosed ? '—' : r.trades}</td>
                  <td style={{ color: 'var(--accent-green)', fontWeight: 700 }}>{r.marketClosed ? '—' : r.wins}</td>
                  <td style={{ color: r.losses > 0 ? 'var(--accent-red)' : 'var(--text-muted)', fontWeight: r.losses > 0 ? 700 : 400 }}>{r.marketClosed ? '—' : r.losses}</td>
                  <td>
                    {r.marketClosed
                      ? <span style={{ color: 'var(--text-muted)', fontStyle: 'italic', fontSize: 12 }}>Closed</span>
                      : <span style={{ fontWeight: 700, fontSize: 15, color: r.winRate >= 75 ? 'var(--accent-green)' : r.winRate >= 60 ? 'var(--accent-amber)' : 'var(--accent-red)' }}>{r.winRate}%</span>
                    }
                  </td>
                  <td>
                    {r.marketClosed
                      ? <span style={{ color: 'var(--text-muted)', fontSize: 12 }}>Weekend — market reopens Sunday ~22:00 UTC</span>
                      : <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                          {r.signals.map((s, j) => (
                            <span key={j} title={`${s.signal} ${s.confidence}%`}
                              style={{ width: 22, height: 22, borderRadius: '50%', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', fontSize: 11, fontWeight: 700,
                                background: s.win ? 'rgba(16,185,129,0.15)' : 'rgba(239,68,68,0.15)',
                                color: s.win ? 'var(--accent-green)' : 'var(--accent-red)',
                                border: `1px solid ${s.win ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}` }}>
                              {s.win ? <IconCheck size={10} /> : '✗'}
                            </span>
                          ))}
                        </div>
                    }
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {results.length === 0 && !running && (
        <div className="empty-state">
          <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)', marginBottom: 12 }}>
            <IconFlask size={44} />
          </div>
          <div className="empty-state-text">Select market type → click Run Backtest<br /><span style={{ fontSize: 12, opacity: 0.6 }}>10 live signal analyses per pair · 65%+ confidence only</span></div>
        </div>
      )}
    </div>
  )
}


// ═══════════════════════════════════════════════════════════════════════
//  ADMIN PAGE
// ═══════════════════════════════════════════════════════════════════════
function AdminPage({ adminSession }: { adminSession: AdminSession }) {
  const [tab, setTab] = useState<AdminTab>('overview')
  const [stats, setStats] = useState<DashboardStats | null>(null)
  const [licenses, setLicenses] = useState<LicenseRow[]>([])
  const [users, setUsers] = useState<UserRow[]>([])
  const [alerts, setAlerts] = useState<any[]>([])
  const [loading, setLoading] = useState(false)

  // Form states
  const [newOwner, setNewOwner] = useState('')
  const [newEmail, setNewEmail] = useState('')
  const [newDays, setNewDays] = useState('365')
  const [newKey, setNewKey] = useState<string | null>(null)
  const [creating, setCreating] = useState(false)
  const [createError, setCreateError] = useState<string | null>(null)

  // Users tab filter: 'all' | 'active'
  const [userFilter, setUserFilter] = useState<'all' | 'active'>('all')

  // Security tab states
  const [newPassword, setNewPassword] = useState('')
  const [changePasswordError, setChangePasswordError] = useState('')
  const [changePasswordSuccess, setChangePasswordSuccess] = useState('')

  // Renew state: which key is being renewed and how many days
  const [renewKey, setRenewKey] = useState<string | null>(null)
  const [renewDays, setRenewDays] = useState('365')
  const [renewLoading, setRenewLoading] = useState(false)
  const [renewMsg, setRenewMsg] = useState<string | null>(null)

  const headers = useCallback(() => ({ 'x-admin-token': adminSession.token, 'Content-Type': 'application/json' }), [adminSession])

  const loadAll = useCallback(async () => {
    setLoading(true)
    try {
      const [statsRes, licRes, usrRes, alertsRes] = await Promise.all([
        fetch(`${API}/admin/dashboard-stats`, { headers: { 'x-admin-token': adminSession.token } }),
        fetch(`${API}/admin/licenses`, { headers: { 'x-admin-token': adminSession.token } }),
        fetch(`${API}/admin/users`, { headers: { 'x-admin-token': adminSession.token } }),
        fetch(`${API}/admin/alerts`, { headers: { 'x-admin-token': adminSession.token } }),
      ])
      if (statsRes.ok) setStats(await statsRes.json())
      if (licRes.ok) setLicenses(await licRes.json())
      if (usrRes.ok) setUsers(await usrRes.json())
      if (alertsRes.ok) setAlerts(await alertsRes.json())
    } catch { /* ignore */ }
    setLoading(false)
  }, [adminSession])

  useEffect(() => { loadAll() }, [loadAll])

  const createLicense = async () => {
    const name = newOwner.trim()
    if (!name) { setCreateError('Please enter a user name.'); return }
    setCreating(true)
    setCreateError(null)
    setNewKey(null)
    try {
      const res = await fetch(`${API}/admin/licenses`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({
          owner: name,
          days: parseInt(newDays) || 365,
          email: newEmail.trim(),
        }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.key) {
          setNewOwner('')
          setNewEmail('')
          setNewKey(data.key)
          setCreateError(null)
          loadAll()
        } else {
          setCreateError('Server returned success but no key was found. Please try again.')
        }
      } else {
        let msg = 'Failed to generate key.'
        try { const err = await res.json(); msg = err.detail || msg } catch { /* ignore */ }
        setCreateError(`Error ${res.status}: ${msg}`)
      }
    } catch (e) {
      setCreateError('Cannot connect to backend. Check your internet or backend server.')
    } finally {
      setCreating(false)
    }
  }

  const toggleLicense = async (key: string, active: boolean) => {
    await fetch(`${API}/admin/licenses/${encodeURIComponent(key)}/status`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify({ is_active: !active }),
    })
    loadAll()
  }

  const deleteLicense = async (key: string) => {
    if (!confirm(`Delete license ${key}?`)) return
    await fetch(`${API}/admin/licenses/${encodeURIComponent(key)}`, {
      method: 'DELETE',
      headers: headers(),
    })
    loadAll()
  }

  const toggleUser = async (id: number, active: boolean) => {
    await fetch(`${API}/admin/users/${id}/status`, {
      method: 'PATCH',
      headers: headers(),
      body: JSON.stringify({ is_active: !active }),
    })
    loadAll()
  }

  const renewLicense = async (key: string) => {
    const days = parseInt(renewDays) || 365
    setRenewLoading(true); setRenewMsg(null)
    try {
      const res = await fetch(`${API}/admin/licenses/${encodeURIComponent(key)}/renew`, {
        method: 'PATCH',
        headers: headers(),
        body: JSON.stringify({ days }),
      })
      if (res.ok) {
        const data = await res.json()
        setRenewMsg(`✅ ${data.message}`)
        setRenewKey(null)
        loadAll()
      } else {
        const err = await res.json()
        setRenewMsg(`❌ ${err.detail || 'Renew failed'}`)
      }
    } catch {
      setRenewMsg('❌ Connection failed')
    }
    setRenewLoading(false)
  }

  const changePassword = async () => {
    if (!newPassword.trim() || newPassword.length < 6) {
      setChangePasswordError('New password must be at least 6 characters.')
      return
    }
    setChangePasswordError(''); setChangePasswordSuccess('')
    try {
      const res = await fetch(`${API}/admin/change-password`, {
        method: 'POST',
        headers: headers(),
        body: JSON.stringify({ new_password: newPassword.trim() }),
      })
      if (res.ok) {
        setChangePasswordSuccess('Admin password changed successfully!')
        setNewPassword('')
      } else {
        const err = await res.json()
        setChangePasswordError(err.detail || 'Failed to change password.')
      }
    } catch {
      setChangePasswordError('Failed to connect to backend.')
    }
  }

  const clearAlerts = async () => {
    try {
      await fetch(`${API}/admin/alerts/clear`, {
        method: 'POST',
        headers: headers(),
      })
      loadAll()
    } catch { /* ignore */ }
  }

  return (
    <div>
      <div className="page-header">
        <h1 className="page-title">Admin Panel</h1>
        <p className="page-subtitle">Admin: Shahzaib · Manage users, licenses, and system settings</p>
      </div>

      {/* Security breach dashboard warnings */}
      {alerts.length > 0 && (
        <div style={{
          marginBottom: 24,
          padding: '16px 20px',
          background: 'linear-gradient(135deg, rgba(239,68,68,0.15), rgba(239,68,68,0.05))',
          border: '1.5px solid rgba(239,68,68,0.35)',
          borderRadius: 12,
          boxShadow: '0 8px 30px rgba(239,68,68,0.1)',
        }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 10, color: 'var(--accent-red)', fontWeight: 800, fontSize: 14 }}>
            <IconAlertTriangle size={18} />
            <span>CRITICAL SECURITY ALERTS ({alerts.length})</span>
            <button 
              onClick={clearAlerts}
              className="admin-btn danger" 
              style={{ padding: '4px 10px', fontSize: 11, marginLeft: 'auto', borderRadius: 6 }}
            >
              Clear Alerts
            </button>
          </div>
          <div style={{ marginTop: 12, display: 'flex', flexDirection: 'column', gap: 8 }}>
            {alerts.slice(0, 3).map((alert, index) => (
              <div key={index} style={{ fontSize: 12, color: 'var(--text-secondary)', background: 'rgba(255,255,255,0.02)', padding: '8px 12px', borderRadius: 8, borderLeft: '3px solid var(--accent-red)' }}>
                <strong>{alert.alert_type}</strong>: {alert.details} <span style={{ float: 'right', opacity: 0.5, fontSize: 10 }}>{fmtDate(alert.created_at)}</span>
              </div>
            ))}
            {alerts.length > 3 && (
              <div style={{ fontSize: 11, color: 'var(--accent-purple)', fontWeight: 600, cursor: 'pointer' }} onClick={() => setTab('security')}>
                + View remaining {alerts.length - 3} security logs under Security tab
              </div>
            )}
          </div>
        </div>
      )}

      {/* Stats */}
      {stats && (
        <div className="stats-grid">
          {/* Clickable: Total Users → Users tab (all) */}
          <div
            className="stat-card purple"
            style={{ cursor: 'pointer' }}
            title="Click to view all users"
            onClick={() => { setUserFilter('all'); setTab('users') }}
          >
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-purple)' }}><IconUsers size={20} /></div>
              <span className="stat-card-label">Total Users</span>
            </div>
            <div className="stat-card-value">{stats.total_users}</div>
          </div>
          {/* Clickable: Active Users → Users tab (active filter) */}
          <div
            className="stat-card green"
            style={{ cursor: 'pointer' }}
            title="Click to view active users"
            onClick={() => { setUserFilter('active'); setTab('users') }}
          >
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-green)' }}><IconCheck size={18} /></div>
              <span className="stat-card-label">Active Users</span>
            </div>
            <div className="stat-card-value">{stats.active_users}</div>
          </div>
          <div className="stat-card red">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-red)' }}><IconHourglass size={18} /></div>
              <span className="stat-card-label">Expired Licenses</span>
            </div>
            <div className="stat-card-value">{stats.expired_licenses}</div>
          </div>
          <div className="stat-card blue">
            <div className="stat-card-header">
              <div className="stat-card-icon" style={{ color: 'var(--accent-blue)' }}><IconActivity size={18} /></div>
              <span className="stat-card-label">Online Now</span>
            </div>
            <div className="stat-card-value">{stats.online_users}</div>
          </div>
        </div>
      )}

      {/* Admin Tabs */}
      <div className="login-tabs" style={{ maxWidth: 650, marginBottom: 24 }}>
        <button className={`login-tab ${tab === 'overview' ? 'active' : ''}`} onClick={() => setTab('overview')}>Overview</button>
        <button className={`login-tab ${tab === 'licenses' ? 'active' : ''}`} onClick={() => setTab('licenses')}>Licenses</button>
        <button className={`login-tab ${tab === 'users' ? 'active' : ''}`} onClick={() => setTab('users')}>Users</button>
        <button className={`login-tab ${tab === 'security' ? 'active' : ''}`} onClick={() => setTab('security')} style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}>
          <IconShield size={14} /> Security & Logs
        </button>
      </div>

      {loading && (
        <div className="loading-overlay" style={{ padding: 30 }}>
          <div className="spinner" />
          <div className="loading-text">Loading…</div>
        </div>
      )}

      {/* Overview Tab */}
      {tab === 'overview' && !loading && (
        <div className="admin-section">
          <div className="admin-section-header">
            <div className="admin-section-title">System Summary</div>
          </div>
          <table className="admin-table">
            <tbody>
              <tr><td style={{ fontWeight: 600 }}>Total Licenses</td><td>{stats?.total_licenses ?? 0}</td></tr>
              <tr><td style={{ fontWeight: 600 }}>Active Licenses</td><td style={{ color: 'var(--accent-green)' }}>{stats?.active_licenses ?? 0}</td></tr>
              <tr><td style={{ fontWeight: 600 }}>Expired Licenses</td><td style={{ color: 'var(--accent-red)' }}>{stats?.expired_licenses ?? 0}</td></tr>
              <tr><td style={{ fontWeight: 600 }}>Total Users</td><td>{stats?.total_users ?? 0}</td></tr>
              <tr><td style={{ fontWeight: 600 }}>Active Users</td><td style={{ color: 'var(--accent-green)' }}>{stats?.active_users ?? 0}</td></tr>
              <tr><td style={{ fontWeight: 600 }}>Online Users</td><td style={{ color: 'var(--accent-blue)' }}>{stats?.online_users ?? 0}</td></tr>
            </tbody>
          </table>
        </div>
      )}

      {/* Licenses Tab */}
      {tab === 'licenses' && !loading && (
        <div className="admin-section">
          <div className="admin-section-header">
            <div className="admin-section-title">License Keys ({licenses.length})</div>
          </div>

          {/* ── New User + License Generator ── */}
          <div style={{ background: 'rgba(124,58,237,0.06)', border: '1px solid rgba(124,58,237,0.15)', borderRadius: 12, padding: '18px 20px', marginBottom: 20 }}>
            <div style={{ fontWeight: 700, fontSize: 14, marginBottom: 12, color: 'var(--accent-purple)' }}>➕ New User — Generate License Key</div>
            <div className="admin-create-form" style={{ flexWrap: 'wrap' }}>
              <input
                placeholder="User name (e.g. Ahmed)"
                value={newOwner}
                onChange={e => { setNewOwner(e.target.value); setNewKey(null); setCreateError(null) }}
                onKeyDown={e => e.key === 'Enter' && createLicense()}
                style={{ flex: 1, minWidth: 150 }}
              />
              <input
                placeholder="User Gmail (Optional)"
                type="email"
                value={newEmail}
                onChange={e => { setNewEmail(e.target.value); setNewKey(null); setCreateError(null) }}
                onKeyDown={e => e.key === 'Enter' && createLicense()}
                style={{ flex: 1, minWidth: 180 }}
              />
              <input placeholder="Days" type="number" value={newDays} onChange={e => setNewDays(e.target.value)} style={{ width: 80, minWidth: 80 }} />
              <button
                className="admin-btn primary"
                onClick={createLicense}
                disabled={creating}
                style={{ whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 6, opacity: creating ? 0.7 : 1 }}
              >
                {creating ? <><span className="spinner" style={{ width: 12, height: 12 }} /> Creating…</> : <><IconKey size={14} /> Generate Key</>}
              </button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>Enter user name & optional Gmail → click Generate Key → license created + user added automatically</div>

            {/* ── Error Display ── */}
            {createError && (
              <div style={{ marginTop: 12, background: 'rgba(239,68,68,0.08)', border: '1.5px solid rgba(239,68,68,0.35)', borderRadius: 8, padding: '10px 14px', fontSize: 12, color: '#f87171', display: 'flex', alignItems: 'center', gap: 8 }}>
                ⚠️ {createError}
              </div>
            )}

            {/* ── Generated Key Display ── */}
            {newKey && (
              <div style={{
                marginTop: 16,
                background: 'rgba(16,185,129,0.08)',
                border: '1.5px solid rgba(16,185,129,0.35)',
                borderRadius: 10,
                padding: '14px 16px',
              }}>
                <div style={{ fontSize: 12, fontWeight: 600, color: 'var(--accent-green)', marginBottom: 8, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
                  <IconCheck size={14} /> License Key Generated Successfully!
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 10, flexWrap: 'wrap' }}>
                  <code style={{
                    flex: 1,
                    fontFamily: 'monospace',
                    fontSize: 16,
                    fontWeight: 800,
                    letterSpacing: 1,
                    color: 'var(--accent-green)',
                    background: 'rgba(16,185,129,0.05)',
                    padding: '8px 12px',
                    borderRadius: 8,
                    border: '1px solid rgba(16,185,129,0.2)',
                    wordBreak: 'break-all',
                  }}>{newKey}</code>
                  <button
                    className="admin-btn success"
                    style={{ whiteSpace: 'nowrap', display: 'inline-flex', alignItems: 'center', gap: 6 }}
                    onClick={() => { navigator.clipboard.writeText(newKey); }}
                  >
                    <IconClipboard size={14} /> Copy Key
                  </button>
                </div>
                <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
                  Share this key with the user. They will use it to login on the License Key screen.
                </div>
              </div>
            )}
          </div>

          {licenses.length === 0 ? (
            <div className="empty-state">
              <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)', marginBottom: 12 }}>
                <IconKey size={44} />
              </div>
              <div className="empty-state-text">No licenses created yet</div>
            </div>
          ) : (
            <>
              {renewMsg && (
                <div style={{ marginBottom: 12, padding: '10px 14px', borderRadius: 8, fontSize: 13, fontWeight: 600,
                  background: renewMsg.startsWith('✅') ? 'rgba(16,185,129,0.1)' : 'rgba(239,68,68,0.1)',
                  color: renewMsg.startsWith('✅') ? 'var(--accent-green)' : 'var(--accent-red)',
                  border: `1px solid ${renewMsg.startsWith('✅') ? 'rgba(16,185,129,0.3)' : 'rgba(239,68,68,0.3)'}` }}>
                  {renewMsg}
                </div>
              )}
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>Key</th>
                    <th>Owner</th>
                    <th>Gmail / Email</th>
                    <th>Device</th>
                    <th>Expires</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {licenses.map(l => {
                    const isExpired = l.expires_at ? new Date(l.expires_at) <= new Date() : false
                    // Find matching user email
                    const matchedUser = users.find(u => u.username.toLowerCase() === l.owner.toLowerCase())
                    const userEmail = matchedUser?.email ?? '—'
                    return (
                      <tr key={l.id}>
                        <td style={{ fontFamily: 'monospace', fontSize: 11 }}>
                          <span title={l.key}>{l.key}</span>
                        </td>
                        <td style={{ fontWeight: 700 }}>{l.owner}</td>
                        <td style={{ fontSize: 11, color: 'var(--text-secondary)' }}>{userEmail}</td>
                        <td style={{ fontSize: 11, color: 'var(--text-muted)' }}>{l.device_id ? l.device_id.slice(0, 12) + '…' : '—'}</td>
                        <td style={{ fontSize: 12, color: isExpired ? 'var(--accent-red)' : 'var(--accent-green)', fontWeight: 600 }}>
                          {fmtDate(l.expires_at)}
                        </td>
                        <td>
                          {isExpired
                            ? <><span className="status-dot expired" /> Expired</>
                            : l.is_active
                              ? <><span className="status-dot active" /> Active</>
                              : <><span className="status-dot inactive" /> Disabled</>
                          }
                        </td>
                        <td>
                          {/* Renew inline */}
                          {renewKey === l.key ? (
                            <div style={{ display: 'flex', gap: 4, alignItems: 'center', flexWrap: 'wrap' }}>
                              <select
                                value={renewDays}
                                onChange={e => setRenewDays(e.target.value)}
                                style={{ fontSize: 11, padding: '3px 6px', borderRadius: 6, background: 'var(--bg-secondary)', color: 'var(--text-primary)', border: '1px solid var(--border)' }}
                              >
                                <option value="30">30 days</option>
                                <option value="90">90 days</option>
                                <option value="180">180 days</option>
                                <option value="365">365 days</option>
                                <option value="730">2 years</option>
                              </select>
                              <button className="admin-btn success" style={{ fontSize: 11, padding: '3px 8px' }}
                                onClick={() => renewLicense(l.key)} disabled={renewLoading}>
                                {renewLoading ? '…' : '✓ Confirm'}
                              </button>
                              <button className="admin-btn" style={{ fontSize: 11, padding: '3px 8px' }}
                                onClick={() => { setRenewKey(null); setRenewMsg(null) }}>✕</button>
                            </div>
                          ) : (
                            <div style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
                              <button
                                className="admin-btn primary"
                                style={{ fontSize: 11, padding: '3px 8px', display: 'inline-flex', alignItems: 'center', gap: 4 }}
                                onClick={() => { setRenewKey(l.key); setRenewDays('365'); setRenewMsg(null) }}
                              >
                                🔄 Renew
                              </button>
                              <button className={`admin-btn ${l.is_active ? 'danger' : 'success'}`}
                                style={{ fontSize: 11, padding: '3px 8px' }}
                                onClick={() => toggleLicense(l.key, !!l.is_active)}>
                                {l.is_active ? 'Disable' : 'Enable'}
                              </button>
                              <button className="admin-btn danger" style={{ fontSize: 11, padding: '3px 8px' }}
                                onClick={() => deleteLicense(l.key)}>Del</button>
                            </div>
                          )}
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
            </>
          )}
        </div>
      )}

      {/* Users Tab */}
      {tab === 'users' && !loading && (() => {
        const filteredUsers = userFilter === 'active' ? users.filter(u => u.is_active) : users
        return (
          <div className="admin-section">
            <div className="admin-section-header">
              <div className="admin-section-title">
                Users ({filteredUsers.length}{userFilter === 'active' ? ' active' : ''})
              </div>
              {/* Filter toggle */}
              <div style={{ display: 'flex', gap: 6, marginLeft: 'auto' }}>
                <button
                  className={`admin-btn ${userFilter === 'all' ? 'primary' : ''}`}
                  style={{ fontSize: 11, padding: '3px 10px' }}
                  onClick={() => setUserFilter('all')}
                >
                  All
                </button>
                <button
                  className={`admin-btn ${userFilter === 'active' ? 'success' : ''}`}
                  style={{ fontSize: 11, padding: '3px 10px' }}
                  onClick={() => setUserFilter('active')}
                >
                  Active Only
                </button>
              </div>
            </div>

            {filteredUsers.length === 0 ? (
              <div className="empty-state">
                <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--text-muted)', marginBottom: 12 }}>
                  <IconUsers size={44} />
                </div>
                <div className="empty-state-text">
                  {userFilter === 'active' ? 'No active users found' : 'No users registered yet'}
                </div>
              </div>
            ) : (
              <table className="admin-table">
                <thead>
                  <tr>
                    <th>ID</th>
                    <th>Username</th>
                    <th>Email</th>
                    <th>Created</th>
                    <th>Subscription</th>
                    <th>Status</th>
                    <th>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredUsers.map(u => (
                    <tr key={u.id}>
                      <td>{u.id}</td>
                      <td style={{ fontWeight: 600 }}>{u.username}</td>
                      <td style={{ fontSize: 12, color: 'var(--text-muted)' }}>{u.email}</td>
                      <td>{fmtDate(u.created_at)}</td>
                      <td>
                        <span style={{ fontSize: 11, padding: '2px 8px', background: 'rgba(124,58,237,0.1)', borderRadius: 50, color: 'var(--accent-purple)' }}>
                          {u.subscription_tier}
                        </span>
                      </td>
                      <td>
                        {u.is_active
                          ? <><span className="status-dot active" /> Active</>
                          : <><span className="status-dot inactive" /> Suspended</>
                        }
                      </td>
                      <td>
                        <button className={`admin-btn ${u.is_active ? 'danger' : 'success'}`} onClick={() => toggleUser(u.id, !!u.is_active)}>
                          {u.is_active ? 'Suspend' : 'Activate'}
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        )
      })()}

      {/* Security & Logs Tab */}
      {tab === 'security' && !loading && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
          
          {/* Change Password Block */}
          <div className="admin-section">
            <div className="admin-section-header">
              <div className="admin-section-title">⚙️ Change Admin Password</div>
            </div>
            
            {changePasswordError && <div className="login-error" style={{ maxWidth: 500, marginBottom: 16 }}>{changePasswordError}</div>}
            {changePasswordSuccess && <div className="login-success" style={{ maxWidth: 500, marginBottom: 16 }}>{changePasswordSuccess}</div>}

            <div style={{ display: 'flex', gap: 12, maxWidth: 500, alignItems: 'flex-end', flexWrap: 'wrap' }}>
              <div style={{ flex: 1, minWidth: 200 }}>
                <label style={{ display: 'block', fontSize: 12, color: 'var(--text-secondary)', marginBottom: 6, fontWeight: 600 }}>New Password</label>
                <input 
                  type="password" 
                  placeholder="Min 6 characters" 
                  value={newPassword}
                  onChange={e => setNewPassword(e.target.value)}
                  style={{ width: '100%' }}
                />
              </div>
              <button 
                onClick={changePassword}
                className="admin-btn primary" 
                style={{ height: 42, padding: '0 20px', whiteSpace: 'nowrap' }}
              >
                Update Password
              </button>
            </div>
            <div style={{ fontSize: 11, color: 'var(--text-muted)', marginTop: 8 }}>
              Change the password you use to log in to the admin workspace. Choose a secure phrase.
            </div>
          </div>

          {/* Recovery Phrase Warning Info */}
          <div style={{
            background: 'rgba(124,58,237,0.04)',
            border: '1px solid rgba(124,58,237,0.15)',
            borderRadius: 12,
            padding: '16px 20px',
          }}>
            <div style={{ fontWeight: 700, fontSize: 13, color: 'var(--accent-purple)', marginBottom: 6, display: 'inline-flex', alignItems: 'center', gap: 6 }}>
              <IconLock size={14} /> Password Recovery Seed Details
            </div>
            <p style={{ fontSize: 12, color: 'var(--text-muted)', lineHeight: 1.5 }}>
              If you ever forget your admin password, you can use the **Secret Recovery Key** generated during backend server startup. 
              This recovery key is securely printed to the server terminal console. Save it in a safe place.
            </p>
          </div>

          {/* Alerts Grid Log */}
          <div className="admin-section">
            <div className="admin-section-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div className="admin-section-title">🛡️ Security Breach & Intrusion Logs</div>
              {alerts.length > 0 && (
                <button 
                  onClick={clearAlerts}
                  className="admin-btn danger" 
                  style={{ padding: '6px 12px', fontSize: 12 }}
                >
                  Clear Logs
                </button>
              )}
            </div>

            {alerts.length === 0 ? (
              <div className="empty-state" style={{ padding: '40px 20px' }}>
                <div className="empty-state-icon" style={{ display: 'flex', justifyContent: 'center', color: 'var(--accent-green)', marginBottom: 12 }}>
                  <IconShield size={44} />
                </div>
                <div className="empty-state-text" style={{ color: 'var(--accent-green)', fontWeight: 600 }}>System Secure. No intrusion alerts recorded.</div>
              </div>
            ) : (
              <div className="scan-results" style={{ marginTop: 12 }}>
                <table className="scan-table" style={{ fontSize: 12 }}>
                  <thead>
                    <tr>
                      <th>Time</th>
                      <th>License key</th>
                      <th>Mismatched Input</th>
                      <th>Alert Type</th>
                      <th>Details</th>
                    </tr>
                  </thead>
                  <tbody>
                    {alerts.map((alert) => (
                      <tr key={alert.id} style={{ borderLeft: '3px solid var(--accent-red)' }}>
                        <td style={{ color: 'var(--text-muted)' }}>{fmtDate(alert.created_at)}</td>
                        <td style={{ fontFamily: 'monospace' }}>{alert.license_key || '—'}</td>
                        <td>
                          <div style={{ fontWeight: 600 }}>{alert.username}</div>
                          <div style={{ fontSize: 10, color: 'var(--text-muted)' }}>{alert.email}</div>
                        </td>
                        <td>
                          <span style={{ 
                            fontSize: 10, 
                            fontWeight: 800, 
                            padding: '2px 8px', 
                            borderRadius: 50, 
                            background: 'rgba(239,68,68,0.12)', 
                            color: 'var(--accent-red)' 
                          }}>
                            {alert.alert_type}
                          </span>
                        </td>
                        <td style={{ color: 'var(--text-secondary)' }}>{alert.details}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
