import test from 'node:test'
import assert from 'node:assert/strict'
import { api } from '../src/api.js'

const originalFetch = globalThis.fetch
const originalWindow = globalThis.window
test.afterEach(() => { globalThis.fetch = originalFetch; globalThis.window = originalWindow })

test('signup sends credentials and the exact backend JSON contract', async () => {
  let request
  globalThis.fetch = async (url, options) => {
    request = { url, ...options }
    return new Response(JSON.stringify({ user: { id: 1, name: 'Alex' } }), { status: 201 })
  }
  const body = { name: 'Alex', email: 'alex@example.com', password: 'example123' }
  assert.equal((await api.signup(body)).user.id, 1)
  assert.equal(request.url, '/backend-api/api/auth/signup')
  assert.equal(request.credentials, 'include')
  assert.equal(request.method, 'POST')
  assert.deepEqual(JSON.parse(request.body), body)
})

test('HTTP 200 clarification remains available to the UI', async () => {
  const clarification = { status: 'needs_clarification', questions: [{ field: 'days', question: 'How many days?' }] }
  globalThis.fetch = async () => new Response(JSON.stringify(clarification))
  assert.deepEqual(await api.extract({ prompt: 'Delhi' }), clarification)
  assert.deepEqual(await api.generate({ prompt: 'Delhi' }), clarification)
})

test('delete accepts empty HTTP 204', async () => {
  globalThis.fetch = async (url, options) => {
    assert.equal(url, '/backend-api/api/v1/itineraries/42')
    assert.equal(options.method, 'DELETE')
    assert.equal(options.credentials, 'include')
    return new Response(null, { status: 204 })
  }
  assert.equal(await api.remove(42), null)
})

test('protected 401 signals session expiration; invalid login stays on the form', async () => {
  let events = 0
  globalThis.window = { dispatchEvent: () => events++ }
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: 'Not authenticated' } }), { status: 401 })
  await assert.rejects(api.list(), error => error.status === 401)
  assert.equal(events, 1)
  await assert.rejects(api.login({ email: 'wrong@example.com', password: 'wrong' }))
  assert.equal(events, 1)
})

test('validation errors retain backend details and request ID', async () => {
  globalThis.fetch = async () => new Response(JSON.stringify({ error: { message: 'Invalid trip', details: [{ message: 'Provide a valid date' }], request_id: 'request-123' } }), { status: 422 })
  await assert.rejects(api.generate({ prompt: 'Delhi' }), error => error.status === 422 && error.message.includes('Provide a valid date') && error.message.includes('request-123'))
})

test('network and non-JSON proxy failures produce readable errors', async () => {
  globalThis.fetch = async () => { throw new TypeError('fetch failed') }
  await assert.rejects(api.health(), /Cannot reach RouteSense/)
  globalThis.fetch = async () => new Response('Bad Gateway', { status: 502 })
  await assert.rejects(api.health(), /Check the backend connection/)
})
