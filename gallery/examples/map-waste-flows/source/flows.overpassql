[out:json][timeout:180];
(
  nwr["amenity"="waste_transfer_station"](49.0,-123.3,49.45,-122.4);
  nwr["amenity"="recycling"]["recycling_type"="centre"](49.0,-123.3,49.45,-122.4);
  nwr["landuse"="landfill"](49.0,-123.3,49.45,-122.4);
  nwr["power"="plant"]["plant:source"="waste"](49.0,-123.3,49.45,-122.4);
  nwr["name"~"(Waste-to-Energy|Maple Ridge Recycling|Maple Ridge Transfer)",i](49.0,-123.3,49.45,-122.4);
);
out center tags;
