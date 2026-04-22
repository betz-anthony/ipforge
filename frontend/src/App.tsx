import { Routes, Route, NavLink } from 'react-router-dom'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'

export default function App() {
  return (
    <div>
      <nav>
        <NavLink to="/">Subnets</NavLink>
        <NavLink to="/addresses">Addresses</NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Subnets />} />
          <Route path="/addresses" element={<Addresses />} />
        </Routes>
      </main>
    </div>
  )
}
