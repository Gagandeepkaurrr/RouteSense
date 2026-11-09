// Demo itinerary. Replace this array with the backend's ordered day/stop response.
// Coordinates use MapLibre's [longitude, latitude] order.
export const initialDays = [
  {
    id: 'day-1',
    label: 'Day 1',
    stops: [
      { id: 'india-gate', name: 'India Gate', time: '09:00 AM', description: 'Iconic war memorial and landmark.', visitMinutes: 45, coordinates: [77.2295, 28.6129] },
      { id: 'humayun', name: "Humayun’s Tomb", time: '10:30 AM', description: 'UNESCO World Heritage Site.', visitMinutes: 90, coordinates: [77.2507, 28.5933] },
      { id: 'lotus', name: 'Lotus Temple', time: '01:00 PM', description: 'A serene Bahá’í House of Worship.', visitMinutes: 75, coordinates: [77.2588, 28.5535] },
    ],
  },
  {
    id: 'day-2',
    label: 'Day 2',
    stops: [
      { id: 'qutub', name: 'Qutub Minar', time: '09:30 AM', description: 'Historic minaret and monument complex.', visitMinutes: 90, coordinates: [77.1855, 28.5244] },
      { id: 'lodhi', name: 'Lodhi Garden', time: '12:00 PM', description: 'Gardens and historic tombs.', visitMinutes: 60, coordinates: [77.2195, 28.5931] },
    ],
  },
]
