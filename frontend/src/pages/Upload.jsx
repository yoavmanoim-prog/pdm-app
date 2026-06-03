import { useState } from 'react'

// Upload page — lets the user pick a PDF and fill in schematic details
export default function Upload() {
  const [form, setForm] = useState({
    part_number: '',
    vehicle_make: '',
    model: '',
    description: ''
  })
  const [file, setFile] = useState(null)   // the PDF file the user picks
  const [status, setStatus] = useState(null) // success or error message
  const [loading, setLoading] = useState(false)

  // Update form state when the user types in any field
  const handleChange = e => setForm({ ...form, [e.target.name]: e.target.value })

  const handleSubmit = async e => {
    e.preventDefault()
    if (!file) return alert('Please select a PDF file')

    // Build a FormData object — this is how browsers send files to a server
    const data = new FormData()
    data.append('file', file)
    data.append('part_number', form.part_number)
    data.append('vehicle_make', form.vehicle_make)
    data.append('model', form.model)
    data.append('description', form.description)

    setLoading(true)
    setStatus(null)

    try {
      const res = await fetch('/api/schematics/upload', {
        method: 'POST',
        body: data  // send the form data (including the file) to the backend
      })
      if (!res.ok) {
        const err = await res.json()
        throw new Error(err.detail || 'Upload failed')
      }
      setStatus({ type: 'success', message: 'Schematic uploaded successfully!' })
      setForm({ part_number: '', vehicle_make: '', model: '', description: '' })
      setFile(null)
    } catch (err) {
      setStatus({ type: 'error', message: err.message })
    } finally {
      setLoading(false)
    }
  }

  return (
    <div>
      <h2>Upload Schematic</h2>

      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '12px', maxWidth: '500px' }}>

        {/* Part number is required — used as the identifier */}
        <input
          name="part_number"
          placeholder="Part Number *"
          value={form.part_number}
          onChange={handleChange}
          required
          style={{ padding: '8px' }}
        />
        <input
          name="vehicle_make"
          placeholder="Vehicle Make (e.g. Toyota)"
          value={form.vehicle_make}
          onChange={handleChange}
          style={{ padding: '8px' }}
        />
        <input
          name="model"
          placeholder="Model (e.g. Corolla)"
          value={form.model}
          onChange={handleChange}
          style={{ padding: '8px' }}
        />
        <textarea
          name="description"
          placeholder="Description"
          value={form.description}
          onChange={handleChange}
          rows={3}
          style={{ padding: '8px' }}
        />

        {/* File picker — only accepts PDF files */}
        <input
          type="file"
          accept=".pdf"
          onChange={e => setFile(e.target.files[0])}
          required
        />

        <button type="submit" disabled={loading} style={{ padding: '10px', cursor: 'pointer' }}>
          {loading ? 'Uploading...' : 'Upload'}
        </button>
      </form>

      {/* Show success or error message after submission */}
      {status && (
        <p style={{ marginTop: '16px', color: status.type === 'success' ? 'green' : 'red' }}>
          {status.message}
        </p>
      )}
    </div>
  )
}
