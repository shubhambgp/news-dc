import { lazy } from 'react'
import { createBrowserRouter, Link, RouterProvider } from 'react-router'

import { EmptyState } from '@/components/common'
import { Layout } from '@/components/Layout'
import HomePage from '@/pages/Home'
import { useTitle } from '@/lib/format'

// Route-level code splitting: the home feed ships in the main bundle, everything else on demand.
const feeds = () => import('@/pages/Feeds')
const TrendingPage = lazy(() => feeds().then((m) => ({ default: m.TrendingPage })))
const RelevantPage = lazy(() => feeds().then((m) => ({ default: m.RelevantPage })))
const TopicsPage = lazy(() => feeds().then((m) => ({ default: m.TopicsPage })))
const TopicPage = lazy(() => feeds().then((m) => ({ default: m.TopicPage })))
const ArticlePage = lazy(() => import('@/pages/Article'))
const SearchPage = lazy(() => import('@/pages/Search'))
const BookmarksPage = lazy(() => import('@/pages/Bookmarks'))
const DashboardPage = lazy(() => import('@/pages/Dashboard'))
const AskPage = lazy(() => import('@/pages/Ask'))
const AdminPage = lazy(() => import('@/pages/Admin'))

function NotFound() {
  useTitle('Not found')
  return (
    <EmptyState>
      Page not found. <Link to="/" className="text-primary underline">Go to the feed</Link>
    </EmptyState>
  )
}

const router = createBrowserRouter([
  {
    element: <Layout />,
    children: [
      { path: '/', element: <HomePage /> },
      { path: '/trending', element: <TrendingPage /> },
      { path: '/relevant', element: <RelevantPage /> },
      { path: '/topics', element: <TopicsPage /> },
      { path: '/topics/:slug', element: <TopicPage /> },
      { path: '/article/:id', element: <ArticlePage /> },
      { path: '/search', element: <SearchPage /> },
      { path: '/bookmarks', element: <BookmarksPage /> },
      { path: '/dashboard', element: <DashboardPage /> },
      { path: '/ask', element: <AskPage /> },
      { path: '/admin', element: <AdminPage /> },
      { path: '*', element: <NotFound /> },
    ],
  },
])

export default function App() {
  return <RouterProvider router={router} />
}
