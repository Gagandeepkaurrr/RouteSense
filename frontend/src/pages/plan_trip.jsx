import { useEffect, useRef, useState } from 'react'
import * as maplibregl from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
import workerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url'
import { api } from '../api.js'
import './plan_trip.css'

const MAP_STYLE = 'https://tiles.openfreemap.org/styles/liberty'
maplibregl.setWorkerUrl(workerUrl)
const EMPTY_ROUTE = { type: 'Feature', geometry: { type: 'LineString', coordinates: [] }, properties: {} }

function routeFeature(geometry) {
  return { type: 'Feature', geometry, properties: {} }
}
const coordinates = (stop) => [stop.coordinates.longitude, stop.coordinates.latitude]
const time = (value) => new Date(value).toLocaleTimeString('en-IN', { timeZone: 'Asia/Kolkata', hour: '2-digit', minute: '2-digit' })
const money = (value) => `₹${Number(value || 0).toLocaleString('en-IN')}`

function TripMap({ stops, legs, selectedLeg, focusedStopId, onSelectStop }) {
  const containerRef = useRef(null)
  const mapRef = useRef(null)
  const markersRef = useRef([])
  const [mapError, setMapError] = useState(false)

  useEffect(() => {
    const map = new maplibregl.Map({
      container: containerRef.current,
      style: MAP_STYLE,
      center: [77.23, 28.58],
      zoom: 11.4,
    })
    mapRef.current = map
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), 'top-right')
    map.on('error', (event) => {
      if (event.error) setMapError(true)
    })
    map.on('load', () => {
      map.addSource('full-route', { type: 'geojson', data: EMPTY_ROUTE })
      map.addLayer({ id: 'full-route-line', type: 'line', source: 'full-route', paint: { 'line-color': '#4683b7', 'line-width': 4, 'line-opacity': 0.6, 'line-dasharray': [2, 2] } })
      map.addSource('next-leg', { type: 'geojson', data: EMPTY_ROUTE })
      map.addLayer({ id: 'next-leg-line', type: 'line', source: 'next-leg', paint: { 'line-color': '#0080ff', 'line-width': 6, 'line-opacity': 0.95 } })
    })
    return () => {
      map.remove()
      mapRef.current = null
    }
  }, [])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function updateMap() {
      map.getSource('full-route')?.setData({ type: 'FeatureCollection', features: legs.filter(leg => leg.geometry).map(leg => routeFeature(leg.geometry)) })
      map.getSource('next-leg')?.setData(selectedLeg?.geometry ? routeFeature(selectedLeg.geometry) : EMPTY_ROUTE)
    }

    if (map.getSource('full-route')) updateMap()
    else map.once('load', updateMap)
    return () => map.off('load', updateMap)
  }, [legs, selectedLeg])

  useEffect(() => {
    const map = mapRef.current
    if (!map) return

    function updateStops() {
      markersRef.current = stops.map((stop, index) => {
        const element = document.createElement('div')
        element.className = `trip-marker ${index === 0 ? 'first' : ''}`
        element.textContent = String.fromCharCode(65 + index)
        element.addEventListener('click', () => onSelectStop(stop.stop_id))
        element.setAttribute('aria-label', `Stop ${index + 1}: ${stop.name}`)
        return new maplibregl.Marker({ element })
          .setLngLat(coordinates(stop))
          .setPopup(new maplibregl.Popup({ offset: 22 }).setText(stop.name))
          .addTo(map)
      })
      if (stops.length) {
        const bounds = new maplibregl.LngLatBounds(coordinates(stops[0]), coordinates(stops[0]))
        stops.forEach((stop) => bounds.extend(coordinates(stop)))
        map.fitBounds(bounds, { padding: 65, maxZoom: 13, duration: 400 })
      }
    }

    if (map.getSource('full-route')) updateStops()
    else map.once('load', updateStops)
    return () => {
      map.off('load', updateStops)
      markersRef.current.forEach(marker => marker.remove())
      markersRef.current = []
    }
  }, [stops, onSelectStop])

  useEffect(() => {
    const stop = stops.find((item) => item.stop_id === focusedStopId)
    if (stop) mapRef.current?.flyTo({ center: coordinates(stop), zoom: 13.5, duration: 500 })
  }, [focusedStopId, stops])

  return (
    <div className="trip-map-wrap">
      <div className="trip-map" ref={containerRef} role="region" aria-label="Map of itinerary stops" />
      {legs.some(leg => leg.geometry) && <div className="map-legend"><span className="legend-next" /> Selected leg <span className="legend-later" /> Road routes</div>}
      {mapError && <div className="map-error">Map tiles could not load. The itinerary remains available on the right.</div>}
    </div>
  )
}

function PlanTrip({ onNavigate, itinerary, onGenerated }) {
  const params = new URLSearchParams(window.location.search)
  const [prompt, setPrompt] = useState(params.get('prompt') || '')
  const [travellers, setTravellers] = useState('')
  const [result, setResult] = useState(null)
  const [answers, setAnswers] = useState({})
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [selectedDayNumber, setSelectedDayNumber] = useState(null)
  const [focusedStopId, setFocusedStopId] = useState(null)
  const requestInFlight = useRef(false)
  const [showExisting, setShowExisting] = useState(!params.has('prompt'))
  const trip = showExisting ? itinerary : null
  const days = trip?.days || []
  const day = days.find(item => item.day_number === selectedDayNumber) || days[0]
  const selectedLeg = focusedStopId
    ? day?.legs.find(leg => leg.to_stop_id === focusedStopId)
    : day?.legs[0]

  async function submit(event) {
    event.preventDefault()
    if (requestInFlight.current) return
    requestInFlight.current = true
    setBusy(true)
    setError('')
    const additions = (result?.questions || []).map(q => {
      const answer = answers[q.field]?.trim()
      return q.field === 'days' && /^\d+$/.test(answer || '') ? `${answer} days` : answer
    }).filter(Boolean)
    const revised = [prompt, ...additions].join(', ')
    const body = { prompt: revised, ...(travellers ? { number_of_travellers: Number(travellers) } : {}) }
    try {
      const response = result?.status === 'ready' ? await api.generate(body) : await api.extract(body)
      setPrompt(revised)
      setAnswers({})
      setResult(response)
      if (response.status === 'generated') {
        onGenerated(response)
        setShowExisting(true)
        setSelectedDayNumber(null)
        setFocusedStopId(null)
      }
    } catch (err) { setError(err.message) } finally { requestInFlight.current = false; setBusy(false) }
  }

  return (
    <main className="trip-page">
      <header className="trip-header">
        <button className="back-button" type="button" onClick={() => onNavigate('/home')} aria-label="Back to home">←</button>
        <div><p className="trip-eyebrow">PLAN YOUR ROUTE</p><h1>Your current journey</h1></div>
        <button className="profile-button" onClick={() => onNavigate('/profile')}>My trips</button>
      </header>
      <form className="integration-form" onSubmit={submit}>
        <label>Tell us about your Delhi trip<textarea required maxLength={4000} value={prompt} onChange={event => { setPrompt(event.target.value); setResult(null); setAnswers({}) }} placeholder="Plan 2 days in Delhi, budget 5000 per person, history and food, starting at 9 am" /></label>
        <label>Travellers (optional)<input type="number" min="1" max="20" value={travellers} onChange={event => { setTravellers(event.target.value); setResult(null) }} /></label>
        {result?.status === 'needs_clarification' && <div role="status">
          <p>{result.reason === 'insufficient_places' ? result.message || 'Too few places matched. Broaden your interests or reduce the number of days.' : 'Please add the missing trip details.'}</p>
          {(result.questions || []).map(q => <label key={q.field}>{q.question}<input required value={answers[q.field] || ''} onChange={event => setAnswers(current => ({ ...current, [q.field]: event.target.value }))} placeholder={q.field === 'days' ? 'For example: 2 days' : 'Add your answer as a trip detail'} /></label>)}
        </div>}
        {result?.status === 'ready' && <p role="status">{result.extracted.city} · {result.extracted.days} days · {money(result.extracted.budget_per_person_inr)} per person · {result.extracted.number_of_travellers} travellers · {result.extracted.start_date} · {result.extracted.start_time} · {result.extracted.pace} · {result.extracted.preferences.join(', ')}{result.extracted.defaulted_fields?.length ? ` · Defaults: ${result.extracted.defaulted_fields.join(', ')}` : ''}</p>}
        {error && <p role="alert">{error}</p>}
        <button className="plan-button" type="submit" disabled={busy}>{busy ? 'Working on your trip…' : result?.status === 'ready' ? 'Generate and save trip' : 'Check trip details'}</button>
      </form>
      {trip && day && <>
        <div className="integration-notices">
          <p>{trip.trip.city} · {trip.trip.start_date} · {trip.trip.number_of_travellers} travellers · Total: {trip.summary.total_distance_km} km, {trip.summary.total_travel_minutes} min travel · {money(trip.summary.estimated_cost_per_person_inr)} per person / {money(trip.summary.estimated_cost_group_inr)} group · Budget remaining per person: {money(trip.summary.budget_remaining_per_person_inr)}</p>
          {!trip.summary.within_budget && <p role="alert">This itinerary exceeds your budget.</p>}
          {trip.warnings.filter(warning => !/\bosrm\b/i.test(warning)).map((warning, index) => <p role="status" key={index}>{warning}</p>)}
          {trip.not_scheduled.length > 0 && <p>Not scheduled: {trip.not_scheduled.join(', ')}</p>}
        </div>
        <div className="trip-layout">
          <section className="map-panel" aria-label="Journey map">
            <div className="map-panel-heading"><div><span className="section-kicker">YOUR ROUTE</span><h2>Explore the journey</h2></div></div>
            <TripMap stops={day.stops} legs={day.legs} selectedLeg={selectedLeg} focusedStopId={focusedStopId} onSelectStop={setFocusedStopId} />
            <p className="map-note">{day.legs.some(leg => leg.geometry) ? 'Select a stop to highlight its incoming road route.' : 'Road lines are unavailable for this day. The map shows your stops.'}</p>
          </section>
          <section className="itinerary-panel" aria-labelledby="itinerary-title">
            <div className="itinerary-heading"><h2 id="itinerary-title">Detailed itinerary</h2><span className="day-count">{days.length} days</span></div>
            <div className="day-tabs" role="group" aria-label="Select itinerary day">{days.map(item => <button key={item.day_number} type="button" className={day.day_number === item.day_number ? 'active' : ''} onClick={() => { setSelectedDayNumber(item.day_number); setFocusedStopId(null) }}>Day {item.day_number}</button>)}</div>
            <div className="trip-stats"><div><small>Day distance / travel</small><strong>{day.total_distance_km} km / {day.total_travel_minutes} min</strong></div><div><small>Day group cost · estimated</small><strong>{money(day.estimated_cost_group_inr)}</strong></div></div>
            {day.schedule_conflicts > 0 && <p role="status">{day.schedule_conflicts} schedule conflicts.</p>}
            <div className="next-leg-card"><span className="next-leg-label">SELECTED LEG</span>{selectedLeg ? <>
              <strong>{day.stops.find(s => s.stop_id === selectedLeg.from_stop_id)?.name} → {day.stops.find(s => s.stop_id === selectedLeg.to_stop_id)?.name}</strong>
              <small>{selectedLeg.distance_km} km · {selectedLeg.predicted_duration_minutes} min estimated travel</small>
              <small>Weather: {selectedLeg.weather.condition_used} · {selectedLeg.weather.fallback_used ? `Estimated / fallback: ${selectedLeg.weather.fallback_reason || selectedLeg.weather.source}` : selectedLeg.weather.forecast_available ? 'Forecast' : 'Estimated'}</small>
            </> : <strong>{focusedStopId ? 'First stop: no incoming travel leg.' : 'No travel legs for this day.'}</strong>}</div>
            <h3 className="stops-heading">Day {day.day_number} · {day.date} · Times in Delhi</h3>
            <ol className="stop-list">{day.stops.map((stop, index) => <li className="stop-item" key={stop.stop_id}>
              <button className="stop-number" type="button" onClick={() => setFocusedStopId(stop.stop_id)}>{String.fromCharCode(65 + index)}</button>
              <div className="stop-details"><span className="stop-time">{time(stop.scheduled_arrival)} – {time(stop.scheduled_departure)}</span><button className="stop-name" type="button" onClick={() => setFocusedStopId(stop.stop_id)}>{stop.name}</button><p>{stop.category}</p>
                <small>{stop.visit_duration_minutes} min visit{stop.visit_duration_estimated ? ' (estimated)' : ''} · {money(stop.estimated_cost_per_person_inr)} per person{stop.cost_estimated ? ' (estimated)' : ''}</small>
                <small>Opening hours: {stop.opening_hours || 'Unavailable'}{stop.opening_hours_estimated ? ' (estimated)' : ''}</small>
                {stop.schedule_conflict && <small role="status">Opening-hours / schedule conflict</small>}
              </div>
            </li>)}</ol>
          </section>
        </div>
      </>}
    </main>
  )
}

export default PlanTrip
