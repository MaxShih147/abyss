const API_BASE = 'http://localhost:8000'

export interface ProgressData {
  iteration: number
  max_iterations: number
  objective: number
  volume_fraction: number
  change: number
  elapsed_seconds: number
}

export interface SubmitResult {
  job_id: string
}

export async function submitOptimization(
  stlBuffer: ArrayBuffer,
  params: Record<string, unknown>,
): Promise<SubmitResult> {
  const form = new FormData()
  form.append('stl_file', new Blob([stlBuffer], { type: 'application/octet-stream' }), 'model.stl')
  form.append('params', JSON.stringify(params))

  const res = await fetch(`${API_BASE}/api/optimize`, { method: 'POST', body: form })
  if (!res.ok) throw new Error(`Submit failed: ${res.status}`)
  return res.json()
}

export function streamProgress(
  jobId: string,
  onProgress: (data: ProgressData) => void,
  onComplete: () => void,
  onError: (msg: string) => void,
): () => void {
  const es = new EventSource(`${API_BASE}/api/optimize/${jobId}/progress`)

  es.onmessage = (event) => {
    const data = JSON.parse(event.data)
    if (data.status === 'complete') {
      es.close()
      onComplete()
    } else if (data.status === 'error') {
      es.close()
      onError(data.message || 'Unknown error')
    } else {
      onProgress(data as ProgressData)
    }
  }

  es.onerror = () => {
    es.close()
    onError('Connection lost')
  }

  // Return cleanup function
  return () => es.close()
}

export async function fetchResult(jobId: string): Promise<ArrayBuffer> {
  const res = await fetch(`${API_BASE}/api/optimize/${jobId}/result`)
  if (!res.ok) throw new Error(`Fetch result failed: ${res.status}`)
  return res.arrayBuffer()
}
