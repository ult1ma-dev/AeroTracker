(function () {
  "use strict";
  const data = JSON.parse(document.getElementById("report-data").textContent);
  const world = JSON.parse(document.getElementById("world-data").textContent);
  const all = data.observations;
  const stats = data.statistics;
  const byId = (id) => document.getElementById(id);
  const number = (value, digits = 0) => value == null ? "нет данных" : new Intl.NumberFormat("ru-RU", {maximumFractionDigits: digits}).format(value);
  const when = (value) => {
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) return "нет данных";
    return new Intl.DateTimeFormat("ru-RU", {day:"2-digit",month:"short",year:"numeric",hour:"2-digit",minute:"2-digit",second:"2-digit",timeZone:"UTC"}).format(date) + " UTC";
  };
  const hasPosition = (plane) => plane.latitude != null && plane.longitude != null;
  const color = (plane) => plane.altitude == null ? "#9aa9bd" : plane.altitude < 3000 ? "#40d6b3" : plane.altitude < 9000 ? "#69aef8" : "#ffb36b";
  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = text;
    return node;
  }
  function metric(id, value, unit) {
    const target = byId(id);
    target.textContent = value == null ? "нет данных" : number(value);
    if (value != null && unit) target.append(" ", element("em", "", unit));
  }
  metric("stat-total", stats.total);
  metric("stat-airborne", stats.airborne);
  metric("stat-altitude", stats.mean_altitude, "м");
  const kilometersPerHour = stats.mean_velocity == null ? null : stats.mean_velocity * 3.6;
  metric("stat-speed", Number.isFinite(kilometersPerHour) ? kilometersPerHour : stats.mean_velocity, Number.isFinite(kilometersPerHour) ? "км/ч" : "м/с");
  byId("stat-status").textContent = "на земле: " + number(stats.on_ground);
  byId("stat-speed-detail").textContent = stats.mean_velocity == null ? "по известным значениям" : number(stats.mean_velocity, 1) + " м/с · по известным значениям";
  byId("snapshot-time").textContent = data.api_timestamp == null ? "Время API: нет данных" : "Снимок: " + when(data.api_timestamp * 1000);
  byId("received-time").textContent = "Получено: " + when(data.received_at);
  byId("registration-total").textContent = "стран: " + number(data.registration_counts.length);
  byId("print-report").addEventListener("click", () => window.print());

  const bounds = [[data.bounds.south, data.bounds.west], [data.bounds.north, data.bounds.east]];
  const map = L.map("flight-map", {attributionControl:false, zoomControl:true, minZoom:1, maxZoom:11, zoomSnap:0.25, scrollWheelZoom:false, preferCanvas:false});
  // Establish the view before vector layers initialize their renderer bounds.
  function resetView() { map.fitBounds(bounds, {padding:[35,35], maxZoom:7, animate:false}); }
  resetView();
  L.control.attribution({prefix:false}).addAttribution("Natural Earth · Leaflet 1.9.4").addTo(map);
  L.geoJSON(world, {interactive:false, style:{color:"#385269", weight:0.65, fillColor:"#21394e", fillOpacity:1}}).addTo(map);
  L.rectangle(bounds, {color:"#e1af73", weight:1.5, opacity:0.8, dashArray:"6 6", fillColor:"#e1af73", fillOpacity:0.025, interactive:false}).addTo(map);
  const markers = L.layerGroup().addTo(map);
  const markerByIcao = new Map();
  byId("reset-view").addEventListener("click", resetView);
  function popup(plane) {
    const box = element("div");
    box.append(element("p", "popup-heading", plane.callsign || "Без позывного"));
    box.append(element("p", "popup-icao", "ICAO24 · " + plane.icao24));
    for (const [label, value] of [["Регистрация", plane.origin_country], ["Высота", plane.altitude == null ? "нет данных" : number(plane.altitude,1) + " м"], ["Скорость", plane.velocity == null ? "нет данных" : number(plane.velocity,1) + " м/с"], ["Состояние", plane.on_ground ? "На земле" : "В воздухе"], ["Координаты", number(plane.latitude,4) + ", " + number(plane.longitude,4)]]) {
      const row = element("div", "popup-row");
      row.append(element("span", "", label), element("strong", "", value));
      box.append(row);
    }
    box.append(element("div", "popup-timestamp", plane.position_time == null ? "Время позиции: нет данных" : "Позиция: " + when(plane.position_time * 1000)));
    return box;
  }

  const svgNS = "http://www.w3.org/2000/svg";
  function svgElement(tag, attributes, text) {
    const node = document.createElementNS(svgNS, tag);
    for (const [name, value] of Object.entries(attributes || {})) node.setAttribute(name, String(value));
    if (text != null) node.textContent = text;
    return node;
  }
  function bars(targetId, rows, labelKey) {
    const target = byId(targetId);
    if (!rows.length || !rows.some((row) => row.count)) {
      target.append(element("p", "chart-empty", "В снимке пока нет самолётов"));
      return;
    }
    const height = Math.max(180, rows.length * 31 + 4);
    const svg = svgElement("svg", {viewBox:`0 0 440 ${height}`, "aria-hidden":"true"});
    const maximum = Math.max(...rows.map((row) => row.count), 1);
    rows.forEach((row, index) => {
      const y = 9 + index * (height / rows.length);
      const label = row[labelKey];
      const text = svgElement("text", {x:0,y:y+12,fill:"#728496","font-size":11,"font-family":"inherit"}, label.length > 24 ? label.slice(0,23) + "…" : label);
      text.append(svgElement("title", {}, label + ": " + number(row.count)));
      svg.append(text);
      svg.append(svgElement("rect", {x:170,y:y,width:222,height:17,rx:4,fill:"#f1f5f8"}));
      if (row.count) svg.append(svgElement("rect", {x:170,y:y,width:Math.max(3, row.count / maximum * 222),height:17,rx:4,fill:row.color || (index === 0 ? "#128f83" : "#84c4bd")}));
      svg.append(svgElement("text", {x:440,y:y+12,fill:"#5e768b","font-size":11,"font-family":"inherit","text-anchor":"end"}, number(row.count)));
    });
    target.append(svg);
  }
  let registrations = data.registration_counts.slice(0,6);
  if (data.registration_counts.length > 6) registrations.push({country:"Другие страны", count:data.registration_counts.slice(6).reduce((sum,row) => sum+row.count,0)});
  bars("registration-chart", registrations, "country");
  bars("altitude-chart", data.altitude_counts, "label");

  function identityCell(plane) {
    const td = element("td");
    td.append(element("strong", "", plane.callsign || "Без позывного"), element("small", "", plane.icao24));
    return td;
  }
  function measurementCell(value, className) {
    return element("td", value == null ? "no-data" : className || "", number(value,1));
  }
  function emptyTable(body, colspan, text) {
    const tr = element("tr", "empty-row");
    const td = element("td", "", text);
    td.colSpan = colspan;
    tr.append(td);
    body.append(tr);
  }
  const topBody = byId("top-body");
  data.top.forEach((plane,index) => {
    const tr = element("tr");
    const rank = element("td", "rank-column");
    rank.append(element("span", "rank-number" + (index < 3 ? " leading" : ""), String(index+1).padStart(2,"0")));
    tr.append(rank, identityCell(plane), element("td", "", plane.origin_country), measurementCell(plane.altitude,"height-cell"), measurementCell(plane.velocity));
    topBody.append(tr);
  });
  if (!data.top.length) emptyTable(topBody,5,"Нет самолётов с известной высотой");
  for (const row of data.registration_counts) {
    const option = element("option", "", row.country + " · " + number(row.count));
    option.value = row.country;
    byId("origin-filter").append(option);
  }
  let sortKey = "altitude";
  let descending = true;
  let filtered = all;
  function sorted(planes) {
    return planes.slice().sort((a,b) => {
      let left = a[sortKey], right = b[sortKey];
      if (sortKey === "callsign") {left = a.callsign || a.icao24; right = b.callsign || b.icao24;}
      if (left == null && right == null) return 0;
      if (left == null) return 1;
      if (right == null) return -1;
      const comparison = typeof left === "string" ? left.localeCompare(right,"ru",{sensitivity:"base"}) : Number(left)-Number(right);
      return descending ? -comparison : comparison;
    });
  }
  function showPlane(plane) {
    const marker = markerByIcao.get(plane.icao24);
    if (!marker) return;
    map.setView([plane.latitude,plane.longitude],Math.max(map.getZoom(),6),{animate:false});
    marker.openPopup();
    byId("flight-map").scrollIntoView({behavior:"smooth",block:"center"});
  }
  function drawTable() {
    const body = byId("aircraft-body");
    body.replaceChildren();
    for (const plane of sorted(filtered)) {
      const tr = element("tr");
      tr.dataset.located = String(hasPosition(plane));
      const state = element("td");
      state.append(element("span","status-pill" + (plane.on_ground ? " ground" : ""),plane.on_ground ? "На земле" : "В воздухе"));
      const position = element("td");
      position.append(element("span","position-pill" + (hasPosition(plane) ? "" : " absent"),hasPosition(plane) ? "↗ На карте" : "нет данных"));
      tr.append(identityCell(plane),element("td","",plane.origin_country),measurementCell(plane.altitude,"height-cell"),measurementCell(plane.velocity),state,position);
      if (hasPosition(plane)) {
        tr.tabIndex = 0;
        tr.title = "Показать на карте: " + (plane.callsign || plane.icao24);
        tr.addEventListener("click",() => showPlane(plane));
        tr.addEventListener("keydown",(event) => {if(event.key === "Enter" || event.key === " "){event.preventDefault();showPlane(plane);}});
      }
      body.append(tr);
    }
    if (!filtered.length) emptyTable(body,6,all.length ? "По выбранным фильтрам самолётов не найдено" : "В снимке нет самолётов");
    byId("table-count").textContent = number(filtered.length) + " из " + number(all.length);
  }
  function refresh() {
    const query = byId("search").value.trim().toLocaleLowerCase("ru");
    const origin = byId("origin-filter").value;
    const status = byId("status-filter").value;
    filtered = all.filter((plane) => (!query || (plane.callsign || "").toLocaleLowerCase("ru").includes(query) || plane.icao24.includes(query)) && (!origin || plane.origin_country === origin) && (status === "all" || (status === "ground" ? plane.on_ground : !plane.on_ground)));
    markers.clearLayers();
    markerByIcao.clear();
    let located = 0;
    for (const plane of filtered) {
      if (!hasPosition(plane)) continue;
      located += 1;
      const marker = L.circleMarker([plane.latitude,plane.longitude], {radius:5.5, color:color(plane), weight:1.3, fillColor:color(plane), fillOpacity:0.85, className:"aircraft-dot"});
      marker.bindPopup(() => popup(plane),{maxWidth:300});
      marker.addTo(markers);
      markerByIcao.set(plane.icao24,marker);
    }
    byId("map-count").textContent = "На карте: " + number(located) + " · в выборке: " + number(filtered.length);
    byId("coordinates-note").textContent = "С координатами: " + number(located) + " · без координат: " + number(filtered.length-located);
    byId("map-empty").hidden = located > 0;
    byId("map-empty").textContent = !all.length ? "В этом снимке самолётов нет" : !filtered.length ? "По выбранным фильтрам самолётов не найдено" : "У выбранных самолётов нет координат. Данные доступны в таблице ниже.";
    drawTable();
  }
  for (const id of ["search","origin-filter","status-filter"]) byId(id).addEventListener(id === "search" ? "input" : "change",refresh);
  byId("reset-filters").addEventListener("click",() => {byId("search").value="";byId("origin-filter").value="";byId("status-filter").value="all";refresh();});
  for (const button of document.querySelectorAll("[data-sort]")) {
    button.addEventListener("click",() => {
      const key = button.dataset.sort;
      descending = sortKey === key ? !descending : key === "altitude" || key === "velocity";
      sortKey = key;
      for (const headerButton of document.querySelectorAll("[data-sort]")) {
        headerButton.querySelector("span").textContent = headerButton === button ? (descending ? "↓" : "↑") : "";
        headerButton.parentElement.removeAttribute("aria-sort");
      }
      button.parentElement.setAttribute("aria-sort",descending ? "descending" : "ascending");
      drawTable();
    });
  }
  refresh();
  // Resizing the printable map keeps SVG paths aligned with the container.
  window.addEventListener("beforeprint",() => {map.invalidateSize({animate:false});resetView();});
  window.addEventListener("afterprint",() => map.invalidateSize({animate:false}));
}());
