import { BrowserRouter as Router, Routes, Route } from 'react-router-dom'
import Layout from './components/Layout'
import Home from './pages/Home'
import WeatherAlert from './pages/WeatherAlert'
import WeatherPredict from './pages/WeatherPredict'
import WeatherNWP from './pages/WeatherNWP'
import WeatherDaily from './pages/WeatherDaily'
import WindPower from './pages/WindPower'
import SolarPower from './pages/SolarPower'
import LoadPower from './pages/LoadPower'
import LoadPrice from './pages/LoadPrice'
import DataShow from './pages/DataShow'
import SpotData from './pages/SpotData'
import SalesDecision from './pages/SalesDecision'
import ScrollDecision from './pages/ScrollDecision'
import UserCenter from './pages/UserCenter'
import PriceOverviewV2 from './pages/PriceOverviewV2'
import ApiTest from './pages/ApiTest'

function App() {
  return (
    <Router>
      <Routes>
        <Route path="/" element={<Layout />}>
          <Route index element={<Home />} />
          <Route path="weather/alert" element={<WeatherAlert />} />
          <Route path="weather/predict" element={<WeatherPredict />} />
          <Route path="weather/nwp" element={<WeatherNWP />} />
          <Route path="weather/daily-predict" element={<WeatherDaily />} />
          <Route path="windpower" element={<WindPower />} />
          <Route path="solarpower" element={<SolarPower />} />
          <Route path="loadpower" element={<LoadPower />} />
          <Route path="loadprice" element={<LoadPrice />} />
          <Route path="data-show" element={<DataShow />} />
          <Route path="spot-data" element={<SpotData />} />
          <Route path="sales-decision" element={<SalesDecision />} />
          <Route path="scroll-decision" element={<ScrollDecision />} />
          <Route path="price-overview" element={<PriceOverviewV2 />} />
          <Route path="api-test" element={<ApiTest />} />
          <Route path="user" element={<UserCenter />} />
        </Route>
      </Routes>
    </Router>
  )
}

export default App
