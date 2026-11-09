import { useEffect, useState } from 'react'
import Home from './pages/home.jsx'
import Profile from './pages/profile.jsx'
import PlanTrip from './pages/plan_trip.jsx'
import Auth from './pages/auth.jsx'
import { api } from './api.js'
import './styles/App.css'
import './styles/theme.css'

function ThemeToggle({ theme, onChange }) {
  return (
    <div className="theme-toggle" aria-label="Color theme">
      <span className={theme === 'light' ? 'current' : ''}>Light</span>
      <button
        type="button"
        role="switch"
        aria-label="Dark mode"
        aria-checked={theme === 'dark'}
        className={`theme-switch ${theme === 'dark' ? 'is-dark' : ''}`}
        onClick={() => onChange(theme === 'light' ? 'dark' : 'light')}
      ><span className="theme-switch-thumb" /></button>
      <span className={theme === 'dark' ? 'current' : ''}>Dark</span>
    </div>
  )
}

function App() {
  const [path, setPath] = useState(window.location.pathname)
  const [user, setUser] = useState(null)
  const [sessionLoading, setSessionLoading] = useState(true)
  const [sessionError, setSessionError] = useState('')
  const [itinerary, setItinerary] = useState(null)
  const [theme, setTheme] = useState(() => localStorage.getItem('routesense-theme') || 'light')

  function navigate(nextPath) {
    window.history.pushState({}, '', nextPath)
    setPath(window.location.pathname)
  }

  useEffect(() => {
    let active = true
    api.me().then(value => { if (active) setUser(value) }).catch(error => {
      if (active && error.status !== 401) setSessionError(error.message)
    }).finally(() => { if (active) setSessionLoading(false) })
    function unauthorized() {
      setUser(null)
      setItinerary(null)
      setSessionError('Your session has expired. Please sign in again.')
    }
    window.addEventListener('routesense:unauthorized', unauthorized)
    return () => { active = false; window.removeEventListener('routesense:unauthorized', unauthorized) }
  }, [])

  async function signOut() {
    await api.logout()
    setUser(null)
    setItinerary(null)
    navigate('/')
  }

  useEffect(() => {
    const handlePopState = () => setPath(window.location.pathname)
    window.addEventListener('popstate', handlePopState)
    return () => window.removeEventListener('popstate', handlePopState)
  }, [])

  useEffect(() => {
    document.documentElement.dataset.theme = theme
    localStorage.setItem('routesense-theme', theme)
  }, [theme])

  let page
  if (sessionLoading) page = <main className="auth-page"><p role="status">Checking your session…</p></main>
  else if (!user) page = <><p role="status">{sessionError}</p><Auth onNavigate={navigate} onAuthenticated={(value) => { setUser(value); setSessionError('') }} /></>
  else if (path === '/profile') page = <Profile onNavigate={navigate} user={user} onLogout={signOut} onOpenTrip={setItinerary} />
  else if (path === '/plan-trip') page = <PlanTrip key={window.location.search} onNavigate={navigate} itinerary={itinerary} onGenerated={setItinerary} />
  else if (path === '/home') page = <Home onNavigate={navigate} />
  else page = <Home onNavigate={navigate} />

  return <>{page}<ThemeToggle theme={theme} onChange={setTheme} /></>
}

export default App
