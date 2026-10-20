# Process model of the simulator

`index.html` is one file. It holds the simulator screen, the process model and the data that the model needs (GP parameters, GP validation, literature cases). It opens from disk with no other file and no network call.

| File | Content |
|---|---|
| `ethane_cracker_model.js` | The process model: reaction (GP of AramcoMech 3.0 in Cantera), acetylene hydrogenation, fired furnace (radiant and convection heat balance, tube metal temperature) or electric heating (closed insulated box: wall conduction loss and power-supply efficiency give the radiant efficiency), compression, cold box (Peng–Robinson flash and refrigeration cascade), C2 splitter, deethanizer, depropanizer, debutanizer, capital, production cost, carbon intensity, break-even, plant checks, by-product shadow prices, fired/electric comparison. |
| `patch_index_v07.py` | Adds the heavy-ends units, furnace results and report tables to the simulator screen. |
| `build_standalone.py` | Puts the screen, the model and the data blocks into `index.html`. |

Reference case (850 °C, 0.35 s, steam/ethane 0.35, 1.5 bar, fired): 468.8 USD/t ethylene, 1,152 kg CO2e/t, break-even electricity price 0.944 cents/kWh.

Electric heating at the same point: 717.2 USD/t, radiant efficiency 0.950 (wall loss 2.0 % of electric power, power-supply efficiency 97 %).
