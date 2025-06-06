import { useEffect, useState } from 'react'
import Head from 'next/head'

export default function Home() {
  const [account, setAccount] = useState(null)
  const [logs, setLogs] = useState([])

  useEffect(() => {
    fetch('http://localhost:8000/account')
      .then(res => res.json())
      .then(setAccount)
      .catch(() => {})
    fetch('http://localhost:8000/logs')
      .then(res => res.json())
      .then(setLogs)
      .catch(() => {})
  }, [])

  return (
    <div className="container">
      <Head>
        <title>Trading Bot Dashboard</title>
      </Head>
      <h1>Trading Bot Dashboard</h1>
      {account && (
        <div className="card">
          <h2>Account</h2>
          <p>Balance: {account.balance}</p>
          <p>Equity: {account.equity}</p>
          <p>Margin: {account.margin}</p>
          <p>Free Margin: {account.free_margin}</p>
          <p>Margin Level: {account.margin_level}</p>
        </div>
      )}
      <div className="card">
        <h2>Logs</h2>
        <pre>{logs.join('\n')}</pre>
      </div>
    </div>
  )
}
