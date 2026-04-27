import { useState } from "react";
import Locker from "./components/Locker";
import Results from "./components/Results";
import "./index.css";

function App() {
  // null = input page; populated object = results page
  const [results, setResults] = useState(null);

  return (
    <div className="App">
      {!results ? (
        <Locker onResults={(data) => setResults(data)} />
      ) : (
        <Results data={results} onBack={() => setResults(null)} />
      )}
    </div>
  );
}

export default App;
