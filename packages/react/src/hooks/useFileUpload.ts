/**
 * Hook for uploading files to the Avatar Engine backend.
 */

import { useCallback, useEffect, useRef, useState } from 'react'
import type { UploadedFile } from '@avatar-engine/core'

export interface UseFileUploadReturn {
  pending: UploadedFile[]
  uploading: boolean
  upload: (file: File) => Promise<UploadedFile | null>
  remove: (fileId: string) => void
  clear: () => void
}

export function useFileUpload(apiBase?: string): UseFileUploadReturn {
  const resolvedApiBase = apiBase ?? '/api/avatar'

  const [pending, setPending] = useState<UploadedFile[]>([])
  const [uploading, setUploading] = useState(false)
  const pendingRef = useRef(pending)
  pendingRef.current = pending

  // Revoke all object URLs on unmount
  useEffect(() => {
    return () => {
      pendingRef.current.forEach((f) => {
        if (f.previewUrl) URL.revokeObjectURL(f.previewUrl)
      })
    }
  }, [])

  const upload = useCallback(async (file: File): Promise<UploadedFile | null> => {
    setUploading(true)
    try {
      const form = new FormData()
      form.append('file', file)

      const res = await fetch(`${resolvedApiBase}/upload`, { method: 'POST', body: form })
      if (!res.ok) {
        const err = await res.json().catch(() => ({ error: res.statusText }))
        console.error('Upload failed:', err.error)
        return null
      }

      const data = await res.json()
      const uploaded: UploadedFile = {
        fileId: data.file_id,
        filename: data.filename,
        mimeType: data.mime_type,
        size: data.size,
        path: data.path,
        previewUrl: file.type.startsWith('image/') ? URL.createObjectURL(file) : undefined,
      }
      setPending((prev) => [...prev, uploaded])
      return uploaded
    } catch (e) {
      console.error('Upload error:', e)
      return null
    } finally {
      setUploading(false)
    }
  }, [resolvedApiBase])

  const remove = useCallback((fileId: string) => {
    setPending((prev) => {
      const item = prev.find((f) => f.fileId === fileId)
      if (item?.previewUrl) URL.revokeObjectURL(item.previewUrl)
      return prev.filter((f) => f.fileId !== fileId)
    })
  }, [])

  const clear = useCallback(() => {
    setPending((prev) => {
      prev.forEach((f) => { if (f.previewUrl) URL.revokeObjectURL(f.previewUrl) })
      return []
    })
  }, [])

  return { pending, uploading, upload, remove, clear }
}
