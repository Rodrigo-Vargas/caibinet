import { useEffect } from 'react'

interface FilePreviewModalProps {
  path: string
  onClose: () => void
}

export default function FilePreviewModal({ path, onClose }: FilePreviewModalProps) {
  useEffect(() => {
    window.electronAPI.openFile(path).finally(onClose)
  }, [path, onClose])

  return null
}
