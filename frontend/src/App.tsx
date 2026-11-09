import { useQuery } from '@tanstack/react-query'
import { Monitor, Moon, Sun } from 'lucide-react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card'
import { getHealth } from '@/lib/api'
import { useTheme, type Theme } from '@/lib/theme'

const NEXT: Record<Theme, Theme> = { system: 'light', light: 'dark', dark: 'system' }
const ICON = { system: Monitor, light: Sun, dark: Moon }

export default function App() {
  const { theme, setTheme } = useTheme()
  const health = useQuery({ queryKey: ['health'], queryFn: getHealth, refetchInterval: 15_000 })
  const ThemeIcon = ICON[theme]

  return (
    <main className="mx-auto flex min-h-screen max-w-xl flex-col gap-6 p-6">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-bold tracking-tight">NewsDC</h1>
        <Button
          variant="outline"
          size="icon"
          onClick={() => setTheme(NEXT[theme])}
          aria-label={`Theme: ${theme}. Switch to ${NEXT[theme]}`}
        >
          <ThemeIcon />
        </Button>
      </header>
      <Card>
        <CardHeader>
          <CardTitle>System status</CardTitle>
        </CardHeader>
        <CardContent aria-live="polite" className="flex flex-wrap items-center gap-2 text-sm">
          {health.isPending && <span>Checking API…</span>}
          {health.isError && (
            <>
              <Badge variant="destructive">API unreachable</Badge>
              <span className="text-muted-foreground">{health.error.message}</span>
              <Button size="sm" variant="outline" onClick={() => health.refetch()}>
                Retry
              </Button>
            </>
          )}
          {health.data && (
            <>
              <Badge variant={health.data.status === 'ok' ? 'default' : 'destructive'}>
                API {health.data.status}
              </Badge>
              <Badge variant={health.data.db === 'ok' ? 'secondary' : 'destructive'}>
                DB {health.data.db}
              </Badge>
              <span className="text-muted-foreground">v{health.data.version}</span>
            </>
          )}
        </CardContent>
      </Card>
    </main>
  )
}
