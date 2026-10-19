import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell } from 'lucide-react'
import { notificationAPI } from '@/api/bank'

export default function NotificationBell() {
  const [open, setOpen] = useState(false)
  const qc = useQueryClient()
  const { data, isError } = useQuery({ queryKey: ['my-notifications'], queryFn: () => notificationAPI.list().then(r => r.data), refetchInterval: 30000 })
  const read = useMutation({ mutationFn: id => notificationAPI.markRead(id), onSuccess: () => qc.invalidateQueries({ queryKey: ['my-notifications'] }) })
  return <div className="relative">
    <button aria-label="Notifications" aria-expanded={open} onClick={() => setOpen(!open)} className="p-2 rounded-lg hover:bg-gray-100 text-gray-500 relative">
      <Bell size={18} />{data?.unread_count > 0 && <span className="absolute -top-1 -right-1 bg-red-600 text-white text-xs rounded-full px-1">{data.unread_count}</span>}
    </button>
    {open && <div role="dialog" aria-label="Notifications" className="absolute right-0 top-10 z-50 bg-white shadow-xl border rounded-lg w-80 max-h-96 overflow-y-auto p-3">
      <h2 className="font-semibold mb-2">Notifications</h2>
      {isError && <p>Notifications could not be loaded.</p>}
      {!isError && !data?.items?.length && <p className="text-sm text-gray-500">No notifications</p>}
      {data?.items?.map(item => <div key={item.id} className="py-2 border-t text-sm">
        <p className="font-medium">{item.subject}</p><p className="text-gray-600 whitespace-pre-wrap break-words">{item.body.length > 300 ? item.body.slice(0, 300) + '…' : item.body}</p>
        {!item.is_read && <button className="text-blue-600 mt-1" disabled={read.isPending} onClick={() => read.mutate(item.id)}>Mark as read</button>}
      </div>)}
    </div>}
  </div>
}
