import { useState } from 'react'
import { api } from '../api.js'
import './auth.css'

function Auth({ onNavigate, onAuthenticated }) {
  const [mode, setMode] = useState('signup')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const isSignup = mode === 'signup'

  async function enterApp(event) {
    event.preventDefault()
    if (busy) return
    const body = Object.fromEntries(new FormData(event.currentTarget))
    setBusy(true)
    setError('')
    try {
      const result = await (isSignup ? api.signup(body) : api.login(body))
      onAuthenticated(result.user)
      onNavigate('/home')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  return (
    <main className="auth-page">
      <div className="auth-shell">
        <aside className="auth-side">
          <div className="auth-brand">
            <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M3 19 37 3 22 37l-5-14L3 19Z" fill="#fff" /><path d="m17 23 20-20-15 34-5-14Z" fill="#79f6fc" /></svg>
            <span><strong>RouteSense</strong><small>Plan · Explore · Navigate</small></span>
          </div>
          <div className="auth-side-copy">
            <span className="auth-kicker">WELCOME TO ROUTESENSE</span>
            <h1>{isSignup ? 'Welcome back!' : 'New around here?'}</h1>
            <p>{isSignup ? 'Already have an account? Sign in to pick up your journey where you left off.' : 'Create your account and start turning travel ideas into journeys.'}</p>
            <button className="auth-outline-button" type="button" onClick={() => setMode(isSignup ? 'login' : 'signup')}>{isSignup ? 'Sign in' : 'Sign up'} <span aria-hidden="true">→</span></button>
          </div>
          <div className="auth-side-art" aria-hidden="true"><span className="auth-orbit" /><span className="auth-dot" /><span className="auth-hill auth-hill-one" /><span className="auth-hill auth-hill-two" /></div>
          <p className="auth-side-foot">The world looks better from somewhere new.</p>
        </aside>

        <section className="auth-form-side" aria-labelledby="auth-title">
          <div className="auth-form-inner">
            <span className="auth-form-kicker">{isSignup ? 'START EXPLORING' : 'YOUR JOURNEY CONTINUES'}</span>
            <h2 id="auth-title">{isSignup ? 'Create account' : 'Welcome back'}</h2>
            <p className="auth-form-intro">{isSignup ? 'Save your plans and keep every trip in one place.' : 'Sign in to see your plans and trip history.'}</p>
            <div className="auth-tabs" role="group" aria-label="Choose sign in or sign up">
              <button type="button" className={!isSignup ? 'active' : ''} aria-pressed={!isSignup} onClick={() => setMode('login')}>Sign in</button>
              <button type="button" className={isSignup ? 'active' : ''} aria-pressed={isSignup} onClick={() => setMode('signup')}>Sign up</button>
            </div>
            <form key={mode} className="auth-form" onSubmit={enterApp}>
              {isSignup && <label>Full name<input type="text" name="name" autoComplete="name" placeholder="Your name" required /></label>}
              <label>Email address<input type="email" name="email" autoComplete="email" placeholder="you@example.com" required /></label>
              <label>Password<input type="password" name="password" autoComplete={isSignup ? 'new-password' : 'current-password'} placeholder="At least 6 characters" minLength={6} required /></label>
              {error && <p role="alert">{error}</p>}
              <button className="auth-submit" type="submit" disabled={busy}>{busy ? 'Please wait…' : isSignup ? 'Create account' : 'Sign in'} <span aria-hidden="true">→</span></button>
            </form>
            <p className="auth-switch-copy">{isSignup ? 'Already have an account?' : 'New to RouteSense?'} <button type="button" onClick={() => setMode(isSignup ? 'login' : 'signup')}>{isSignup ? 'Sign in' : 'Create an account'}</button></p>
            <p className="auth-demo-note">Plan and save your Delhi journeys.</p>
          </div>
        </section>
      </div>
    </main>
  )
}

export default Auth
