import { useEffect, useState } from 'react'
import { api } from '../api.js'
import './profile.css'

const filters = ['All trips', 'generated', 'planned', 'completed']

function Profile({ onNavigate, user, onLogout, onOpenTrip }) {
  const [savedTrips, setSavedTrips] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    let active = true
    api.list().then(trips => { if (active) setSavedTrips(trips) }).catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [])
  async function openTrip(id) {
    setBusy(true); setError('')
    try { onOpenTrip(await api.get(id)); onNavigate('/plan-trip') } catch (err) { setError(err.message); if (err.status === 404) setSavedTrips(current => current.filter(trip => trip.trip_id !== id)) } finally { setBusy(false) }
  }
  async function removeTrip(id) {
    setBusy(true); setError('')
    try { await api.remove(id); setSavedTrips(current => current.filter(trip => trip.trip_id !== id)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const historyTrips = savedTrips.map(trip => ({ ...trip, id: trip.trip_id, title: `${trip.city} journey`, destination: trip.city, dates: trip.start_date, days: trip.number_of_days, stops: [], color: 'mint' }))
  const [search, setSearch] = useState('')
  const [status, setStatus] = useState('All trips')

  const totalDays = savedTrips.reduce((sum, trip) => sum + trip.number_of_days, 0)
  const visibleTrips = historyTrips.filter((trip) => {
    const matchesStatus = status === 'All trips' || trip.status === status
    const query = search.trim().toLowerCase()
    const matchesSearch = !query || [trip.title, trip.destination, ...trip.stops]
      .some((value) => value.toLowerCase().includes(query))
    return matchesStatus && matchesSearch
  })

  return (
    <main className="profile-page">
      <header className="profile-header">
        <button className="profile-back" type="button" onClick={() => onNavigate('/home')} aria-label="Back to home">←</button>
        <div>
          <p className="profile-eyebrow">YOUR TRAVEL SPACE</p>
          <h1>My profile</h1>
        </div>
        <button className="profile-plan-button" type="button" onClick={() => onNavigate('/plan-trip')}>View current journey <span aria-hidden="true">↗</span></button>
      </header>

      <div className="profile-content">
        <section className="profile-intro" aria-labelledby="welcome-title">
          <div className="profile-avatar" aria-hidden="true">{user.name.slice(0, 2).toUpperCase()}</div>
          <div className="profile-intro-copy">
            <span className="profile-overline">EXPLORER PROFILE</span>
            <h2 id="welcome-title">{user.name}, your journeys in one place.</h2>
            <p>Look back at where you have been and keep track of what is coming next.</p>
          </div>
          <div className="profile-intro-art" aria-hidden="true"><span className="art-sun" /><span className="art-hill art-hill-back" /><span className="art-hill art-hill-front" /><span className="art-route" /><span className="art-pin">●</span></div>
        </section>

        <section className="profile-stats" aria-label="Trip summary">
          <div className="profile-stat"><span>Saved trips</span><strong>{historyTrips.length}</strong><small>Your itinerary library</small></div>
          <div className="profile-stat"><span>Days planned</span><strong>{totalDays}</strong><small>Across saved itineraries</small></div>
          <div className="profile-stat"><span>Latest trip</span><strong>{historyTrips[0]?.destination || '—'}</strong><small>{historyTrips[0]?.dates || 'Plan your first trip'}</small></div>
          <div className="profile-stat"><span>Planned journeys</span><strong>{savedTrips.filter(trip => trip.status === 'planned').length}</strong><small>Ready to explore</small></div>
        </section>

        <section className="history-section" aria-labelledby="history-title">
          <div className="history-heading">
            <div><p className="profile-eyebrow">THE JOURNEY SO FAR</p><h2 id="history-title">Trip history</h2><p>Find a trip and open it to see the stops.</p></div>
            <button className="trip-details-button" disabled={busy} onClick={async () => { setBusy(true); try { await onLogout() } catch (err) { setError(err.message) } finally { setBusy(false) } }}>Sign out</button>
          </div>
          <div className="history-toolbar">
            <label className="history-search"><span aria-hidden="true">⌕</span><input type="search" value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Search destinations or stops" aria-label="Search trip history" /></label>
            <div className="history-filters" role="group" aria-label="Filter trips by status">
              {filters.map((filter) => <button key={filter} type="button" className={status === filter ? 'active' : ''} aria-pressed={status === filter} onClick={() => setStatus(filter)}>{filter}</button>)}
            </div>
          </div>

          {error && <p role="alert">{error}</p>}
          {loading && <p role="status">Loading saved trips…</p>}
          {visibleTrips.length === 0 ? (
            <div className="history-empty"><strong>No trips found</strong><p>Try a different search or status filter.</p></div>
          ) : (
            <div className="history-grid">
              {visibleTrips.map((trip) => {
                return <article className={`history-card ${trip.color}`} key={trip.id}>
                  <div className="history-card-art" aria-hidden="true"><span className="card-sun" /><span className="card-hill card-hill-back" /><span className="card-hill card-hill-front" /><span className="card-path" /></div>
                  <div className="history-card-body">
                    <div className="history-card-top"><span className={`status-pill ${trip.status.toLowerCase()}`}>{trip.status}</span><span className="trip-dates">{trip.dates}</span></div>
                    <h3>{trip.title}</h3>
                    <p className="trip-destination">⌖ &nbsp;{trip.destination}</p>
                    <div className="history-card-meta"><span>{trip.days} days</span><span>{trip.number_of_travellers} travellers</span>{trip.distanceKm != null && <span>{trip.distanceKm} km</span>}</div>
                    <button className="trip-details-button" type="button" disabled={busy} onClick={() => openTrip(trip.id)}>Open itinerary →</button>
                    <button className="trip-details-button" type="button" disabled={busy} onClick={() => removeTrip(trip.id)}>Delete trip</button>
                  </div>
                </article>
              })}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default Profile
