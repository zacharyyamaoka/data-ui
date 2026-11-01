[out:json][timeout:180];
area["ISO3166-2"="CA-BC"][admin_level=4]->.bc;
(
  nwr["amenity"="waste_transfer_station"](area.bc);
  nwr["landuse"="landfill"](area.bc);
  nwr["amenity"="recycling"]["recycling_type"="centre"](area.bc);
);
out center tags;
