import { useState } from 'react'
const filters = [
  { label: 'Time', hint: 'Travel duration', icon: 'calendar', tone: 'mint', options: ['1 day', '2 days', '3 days', '5 days'] },
  { label: 'Budget', hint: 'Your spending range', icon: 'rupee', tone: 'peach', options: ['budget 1000 per person', 'budget 3000 per person', 'budget 5000 per person', 'budget 10000 per person'] },
  { label: 'Interests', hint: 'Things you love', icon: 'heart', tone: 'rose', options: ['nature and parks', 'food', 'history and heritage', 'shopping'] },
  { label: 'Pace', hint: 'Your exploring pace', icon: 'car', tone: 'blue', options: ['relaxed pace', 'normal pace', 'packed pace'] },
]
function Icon({ name, size = 24 }) {
  const paths = {
    pin: <><path d="M20 10c0 5-8 12-8 12S4 15 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2" /><path d="M7 3v4M17 3v4M3 10h18" /></>,
    heart: <path d="M20.8 4.6a5.5 5.5 0 0 0-7.8 0L12 5.7l-1.1-1.1a5.5 5.5 0 0 0-7.8 7.8L12 21l8.8-8.6a5.5 5.5 0 0 0 0-7.8Z" />,
    car: <><path d="m5 11 2-6h10l2 6M4 11h16v8H4zM4 15h16M7 19v2M17 19v2" /><circle cx="7.5" cy="15" r="1" /><circle cx="16.5" cy="15" r="1" /></>,
    arrow: <><path d="M4 12h16M14 6l6 6-6 6" /></>,
    user: <><circle cx="12" cy="8" r="4" /><path d="M4 21a8 8 0 0 1 16 0" /></>,
  }

  if (name === 'rupee') return <span className="rupee-icon" aria-hidden="true">₹</span>

  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{paths[name]}</svg>
}

function Landscape() {
  return (
    <svg className="landscape" viewBox="0 0 550 285" role="img" aria-label="Illustration of mountains and a winding route">
      <defs>
        <linearGradient id="mountain" x1="0" y1="0" x2="1" y2="1"><stop stopColor="#87cdee" /><stop offset="1" stopColor="#4683b7" /></linearGradient>
        <linearGradient id="pin" x1="0" y1="0" x2="0" y2="1"><stop stopColor="#0080ff" /><stop offset="1" stopColor="#0147ab" /></linearGradient>
      </defs>
      <circle cx="224" cy="48" r="25" fill="#79f6fc" />
      <path d="M45 109c10-17 25-16 32 0 9-10 23-9 31 7H38Z" fill="#95cadb" />
      <path d="M420 58c11-14 21-14 32 0 8-6 18-5 24 6h-67Z" fill="#81d8d0" />
      <path d="m42 237 149-111 78 63 53-43 115 89Z" fill="#87cdee" />
      <path d="m284 234 127-117 112 116Z" fill="url(#mountain)" />
      <path d="m0 269 58-43 64 43Zm320 0 78-42 113 42Z" fill="#95cadb" />
      <path d="M308 260c-55-25 75-28 55-62-12-21-85-19-26-43" fill="none" stroke="#008081" strokeWidth="3" strokeLinecap="round" />
      <path d="M311 93c0-18 14-32 32-32s32 14 32 32c0 21-32 56-32 56s-32-35-32-56Z" fill="url(#pin)" />
      <circle cx="343" cy="93" r="10" fill="#fff" />
      <path d="M78 255v-38m-8 21 8-34 8 34Zm365 9v-34m-10 25 10-36 10 36Z" fill="#42e0d1" stroke="#003152" strokeWidth="2" strokeLinejoin="round" />
      <path d="M109 267v-22m-5 14 5-24 5 24Z" fill="#81d8d0" stroke="#003152" strokeWidth="1.5" />
    </svg>
  )
}

function Home({ onNavigate }) {
  const [destination, setDestination] = useState('')
  const [selectedOptions, setSelectedOptions] = useState({})
  const [openFilter, setOpenFilter] = useState(null)

  function chooseOption(label, option) {
    setSelectedOptions((current) => ({
      ...current,
      [label]: current[label] === option ? null : option,
    }))
  }

  // Include selected preferences in the natural-language request.
  const selectedPromptParts = filters
    .filter((filter) => selectedOptions[filter.label])
    .map((filter) => `${filter.label}: ${selectedOptions[filter.label]}`)
  const searchPrompt = [destination.trim(), ...selectedPromptParts].filter(Boolean).join(', ')
  const activeFilter = filters.find((filter) => filter.label === openFilter)

  function planTrip(event) {
    event.preventDefault()
    const query = new URLSearchParams({ prompt: searchPrompt })
    onNavigate(`/plan-trip?${query}`)
  }

  return (
    <main className="home-page">
      <header className="topbar">
        <a className="brand" href="/home" onClick={(event) => { event.preventDefault(); onNavigate('/home') }} aria-label="RouteSense home">
          <svg viewBox="0 0 40 40" fill="none" aria-hidden="true"><path d="M3 19 37 3 22 37l-5-14L3 19Z" fill="#0147ab" /><path d="m17 23 20-20-15 34-5-14Z" fill="#01ffff" /></svg>
          <span><strong>RouteSense</strong><small>Plan&nbsp; Explore&nbsp; Navigate</small></span>
        </a>
        <button className="profile-button" type="button" onClick={() => onNavigate('/profile')} aria-label="Open profile"><Icon name="user" /></button>
      </header>

      <div className="home-content">
        <section className="hero-section" aria-labelledby="hero-title">
          <div className="hero-copy">
            <p className="eyebrow">EXPLORE SMARTER</p>
            <h1 id="hero-title">Your next journey<br /><span>starts here.</span></h1>
            <p className="hero-description">Plan personalized trips, get smarter routes, and explore Delhi with RouteSense.</p>
          </div>
          <Landscape />
        </section>

        <form className="search-form" onSubmit={planTrip}>
          <Icon name="pin" size={25} />
          <div className="search-fields">
            <input aria-label="Destination or trip idea" value={destination} onChange={(event) => setDestination(event.target.value)} required placeholder="Describe your Delhi trip: days, budget and interests" />
            {selectedPromptParts.length > 0 && <p className="prompt-preview" aria-live="polite">Prompt: {searchPrompt}</p>}
          </div>
          <button className="plan-button" type="submit">Plan My Trip <Icon name="arrow" size={20} /></button>
        </form>

        <section className="filter-section" aria-label="Add trip preferences to search prompt">
          {filters.map((filter) => (
            <button key={filter.label} className={`filter-card ${filter.tone} ${selectedOptions[filter.label] ? 'selected' : ''}`} type="button" onClick={() => setOpenFilter((current) => current === filter.label ? null : filter.label)} aria-expanded={openFilter === filter.label} aria-controls="filter-options">
              <Icon name={filter.icon} size={31} />
              <span><strong>{filter.label}</strong><small>{selectedOptions[filter.label] || filter.hint}</small></span>
            </button>
          ))}
          {activeFilter && (
            <div className="filter-options" id="filter-options" aria-label={`${activeFilter.label} options`}>
              <span className="filter-options-title">Choose {activeFilter.label.toLowerCase()}</span>
              {activeFilter.options.map((option) => (
                <button key={option} type="button" className={`option-button ${selectedOptions[activeFilter.label] === option ? 'active' : ''}`} aria-pressed={selectedOptions[activeFilter.label] === option} onClick={() => chooseOption(activeFilter.label, option)}>{option}</button>
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  )
}

export default Home
