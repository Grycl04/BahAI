import { db } from "../firebase-common.js";
import {
  collection,
  doc,
  getDocs,
  limit,
  query,
  Timestamp,
  where,
  writeBatch
} from "https://www.gstatic.com/firebpy -m http.server 5500asejs/12.4.0/firebase-firestore.js";

const TARGET_TOTAL = 120;
const BASE_COUNTS = {
  rent: 40,
  sale: 35,
  lease: 25
};

const BATANGAS_LOCATIONS = [
  { city: "Agoncillo", lat: 13.934, lng: 120.933 },
  { city: "Alitagtag", lat: 13.865, lng: 121.005 },
  { city: "Balayan", lat: 13.938, lng: 120.732 },
  { city: "Balete", lat: 14.031, lng: 121.094 },
  { city: "Batangas City", lat: 13.7565, lng: 121.0583 },
  { city: "Bauan", lat: 13.791, lng: 121.011 },
  { city: "Calaca", lat: 13.932, lng: 120.813 },
  { city: "Calatagan", lat: 13.832, lng: 120.632 },
  { city: "Cuenca", lat: 13.904, lng: 121.052 },
  { city: "Ibaan", lat: 13.818, lng: 121.133 },
  { city: "Laurel", lat: 14.053, lng: 120.919 },
  { city: "Lemery", lat: 13.880, lng: 120.911 },
  { city: "Lian", lat: 14.033, lng: 120.650 },
  { city: "Lipa City", lat: 13.9411, lng: 121.1631 },
  { city: "Lobo", lat: 13.648, lng: 121.211 },
  { city: "Mabini", lat: 13.750, lng: 120.940 },
  { city: "Malvar", lat: 14.044, lng: 121.157 },
  { city: "Mataasnakahoy", lat: 13.959, lng: 121.113 },
  { city: "Nasugbu", lat: 14.072, lng: 120.633 },
  { city: "Padre Garcia", lat: 13.881, lng: 121.214 },
  { city: "Rosario", lat: 13.843, lng: 121.199 },
  { city: "San Jose", lat: 13.878, lng: 121.106 },
  { city: "San Juan", lat: 13.828, lng: 121.397 },
  { city: "San Luis", lat: 13.854, lng: 120.933 },
  { city: "San Nicolas", lat: 13.931, lng: 120.950 },
  { city: "San Pascual", lat: 13.808, lng: 121.022 },
  { city: "Santa Teresita", lat: 13.866, lng: 120.950 },
  { city: "Santo Tomas", lat: 14.108, lng: 121.144 },
  { city: "Taal", lat: 13.879, lng: 120.923 },
  { city: "Talisay", lat: 14.100, lng: 121.021 },
  { city: "Tanauan City", lat: 14.0862, lng: 121.1498 },
  { city: "Taysan", lat: 13.866, lng: 121.097 },
  { city: "Tingloy", lat: 13.659, lng: 120.883 },
  { city: "Tuy", lat: 14.018, lng: 120.729 }
];

const STREET_NAMES = [
  "Rizal",
  "Bonifacio",
  "Mabini",
  "A. Mabini",
  "Luna",
  "Burgos",
  "Quezon",
  "P. Zamora",
  "J.P. Laurel",
  "Del Pilar"
];

const BARANGAYS = [
  "Poblacion",
  "San Isidro",
  "San Roque",
  "Sampaguita",
  "Mabuhay",
  "Santa Cruz",
  "Bagong Silang",
  "Malinis",
  "Masagana",
  "Balintawak"
];

const RENT_TYPES = ["Boarding House", "Apartment", "Studio", "House"];
const SALE_TYPES = ["House & Lot", "Condo", "Land", "Commercial Property"];
const LEASE_TYPES = ["Commercial Unit", "Office", "Warehouse", "Land"];

const FURNISHING_OPTIONS = ["Furnished", "Semi-Furnished", "Unfurnished"];
const SALE_PAYMENT_TYPES = ["Outright", "Installment", "Bank Financing"];

function randInt(min, max) {
  return Math.floor(Math.random() * (max - min + 1)) + min;
}

function randFloat(min, max, decimals = 6) {
  const value = Math.random() * (max - min) + min;
  return Number(value.toFixed(decimals));
}

function pickRandom(arr) {
  return arr[randInt(0, arr.length - 1)];
}

function createAddress(city) {
  const houseNo = randInt(1, 999);
  const street = pickRandom(STREET_NAMES);
  const brgy = pickRandom(BARANGAYS);
  return `${houseNo} ${street} St., Brgy. ${brgy}, ${city}, Batangas`;
}

function jitterCoordinates(baseLat, baseLng) {
  return {
    latitude: randFloat(baseLat - 0.03, baseLat + 0.03),
    longitude: randFloat(baseLng - 0.03, baseLng + 0.03)
  };
}

function createImages(seed) {
  return [
    `https://picsum.photos/seed/${seed}-1/1280/720`,
    `https://picsum.photos/seed/${seed}-2/1280/720`,
    `https://picsum.photos/seed/${seed}-3/1280/720`
  ];
}

function createFeatures(category) {
  const common = {
    parking: Math.random() > 0.35,
    wifiReady: Math.random() > 0.25,
    petFriendly: Math.random() > 0.55,
    cctv: Math.random() > 0.4,
    gated: Math.random() > 0.5,
    nearTransport: Math.random() > 0.35,
    nearSchools: Math.random() > 0.45,
    nearMarket: Math.random() > 0.3
  };

  if (category === "Commercial") {
    common.backupPower = Math.random() > 0.5;
    common.loadingArea = Math.random() > 0.6;
    common.fireSystem = Math.random() > 0.35;
  }

  return common;
}

function getDistribution(targetTotal = TARGET_TOTAL) {
  const baseTotal = BASE_COUNTS.rent + BASE_COUNTS.sale + BASE_COUNTS.lease;
  const counts = { ...BASE_COUNTS };

  if (targetTotal <= baseTotal) return counts;

  // Fill extras while keeping base distribution intact.
  const extras = targetTotal - baseTotal;
  const order = ["rent", "sale", "lease"];
  for (let i = 0; i < extras; i += 1) {
    counts[order[i % order.length]] += 1;
  }
  return counts;
}

async function getOwnerPools() {
  const fallback = {
    landlords: Array.from({ length: 8 }, (_, i) => `seed-landlord-${i + 1}`),
    brokers: Array.from({ length: 8 }, (_, i) => `seed-broker-${i + 1}`)
  };

  try {
    const snap = await getDocs(
      query(collection(db, "users"), where("role", "in", ["landlord", "broker"]))
    );

    const landlords = [];
    const brokers = [];
    snap.forEach((d) => {
      const data = d.data() || {};
      if (data.role === "landlord") landlords.push(d.id);
      if (data.role === "broker") brokers.push(d.id);
    });

    return {
      landlords: landlords.length ? landlords : fallback.landlords,
      brokers: brokers.length ? brokers : fallback.brokers
    };
  } catch (error) {
    console.warn("Could not fetch owner pools; using fallback IDs.", error);
    return fallback;
  }
}

function createRentListing(index, ownerId) {
  const loc = pickRandom(BATANGAS_LOCATIONS);
  const coords = jitterCoordinates(loc.lat, loc.lng);
  const type = pickRandom(RENT_TYPES);
  const bedrooms = type === "Studio" ? 0 : randInt(1, 4);
  const bathrooms = randInt(1, 2);
  const monthlyRent = randInt(2500, 25000);
  const furnishing = pickRandom(FURNISHING_OPTIONS);

  const title = `${furnishing} ${type} for Rent in ${loc.city}`;
  return {
    title,
    description: `${title}. Ideal for students, professionals, or small families. Near key establishments and transport routes.`,
    category: "Residential",
    type,
    propertyType: type,
    listingType: "FOR RENT",
    status: "active",
    price: monthlyRent,
    monthlyRent,
    bedrooms,
    bathrooms,
    furnishing,
    city: loc.city,
    province: "Calabarzon",
    fullAddress: createAddress(loc.city),
    location: loc.city,
    latitude: coords.latitude,
    longitude: coords.longitude,
    images: createImages(`rent-${index}`),
    photos: createImages(`rent-photo-${index}`),
    features: createFeatures("Residential"),
    ownerId,
    views: randInt(5, 400),
    createdAt: Timestamp.fromDate(new Date(Date.now() - randInt(1, 120) * 86400000))
  };
}

function createSaleListing(index, ownerId) {
  const loc = pickRandom(BATANGAS_LOCATIONS);
  const coords = jitterCoordinates(loc.lat, loc.lng);
  const type = pickRandom(SALE_TYPES);
  const bedrooms = type === "Land" || type === "Commercial Property" ? 0 : randInt(1, 5);
  const bathrooms = type === "Land" ? 0 : randInt(1, 4);
  const floorArea = randInt(30, 450);
  const lotArea = randInt(50, 1200);
  const yearBuilt = randInt(1990, 2025);
  const saleType = pickRandom(SALE_PAYMENT_TYPES);
  const price = randInt(500000, 15000000);

  const title = `${type} for Sale in ${loc.city}`;
  return {
    title,
    description: `${title} with excellent value and growth potential. Suitable for end-use or long-term investment.`,
    category: type === "Commercial Property" ? "Commercial" : "Residential",
    type,
    propertyType: type,
    listingType: "FOR SALE",
    status: "active",
    price,
    salePrice: price,
    bedrooms,
    bathrooms,
    floorArea,
    lotArea,
    yearBuilt,
    saleType,
    city: loc.city,
    province: "Calabarzon",
    fullAddress: createAddress(loc.city),
    location: loc.city,
    latitude: coords.latitude,
    longitude: coords.longitude,
    images: createImages(`sale-${index}`),
    photos: createImages(`sale-photo-${index}`),
    features: createFeatures(type === "Commercial Property" ? "Commercial" : "Residential"),
    ownerId,
    views: randInt(20, 900),
    createdAt: Timestamp.fromDate(new Date(Date.now() - randInt(1, 240) * 86400000))
  };
}

function createLeaseListing(index, ownerId) {
  const loc = pickRandom(BATANGAS_LOCATIONS);
  const coords = jitterCoordinates(loc.lat, loc.lng);
  const type = pickRandom(LEASE_TYPES);
  const floorArea = randInt(40, 950);
  const lotArea = randInt(70, 3000);
  const monthlyLeaseRate = randInt(10000, 200000);
  const leaseTerm = randInt(1, 10);

  const title = `${type} for Lease in ${loc.city}`;
  return {
    title,
    description: `${title}. Strategic commercial location with flexible setup and long-term business potential.`,
    category: "Commercial",
    type,
    propertyType: type,
    listingType: "FOR LEASE",
    status: "active",
    price: monthlyLeaseRate,
    monthlyLeaseRate,
    floorArea,
    lotArea,
    leaseTerm: `${leaseTerm} year${leaseTerm > 1 ? "s" : ""}`,
    city: loc.city,
    province: "Calabarzon",
    fullAddress: createAddress(loc.city),
    location: loc.city,
    latitude: coords.latitude,
    longitude: coords.longitude,
    images: createImages(`lease-${index}`),
    photos: createImages(`lease-photo-${index}`),
    features: createFeatures("Commercial"),
    ownerId,
    views: randInt(10, 700),
    createdAt: Timestamp.fromDate(new Date(Date.now() - randInt(1, 180) * 86400000))
  };
}

async function commitInBatches(docs, batchSize = 400) {
  for (let i = 0; i < docs.length; i += batchSize) {
    const chunk = docs.slice(i, i + batchSize);
    const batch = writeBatch(db);
    chunk.forEach((propertyDoc) => {
      const ref = doc(collection(db, "properties"));
      batch.set(ref, propertyDoc);
    });
    await batch.commit();
  }
}

export async function seedProperties(options = {}) {
  const targetTotal = Number.isFinite(options.targetTotal) ? options.targetTotal : TARGET_TOTAL;
  const force = options.force === true;

  try {
    const existingSnap = await getDocs(query(collection(db, "properties"), limit(1)));
    if (!force && !existingSnap.empty) {
      console.warn(
        "Aborted: properties collection already has data. Pass { force: true } to seed anyway."
      );
      return;
    }

    const distribution = getDistribution(targetTotal);
    const ownerPools = await getOwnerPools();

    const docs = [];
    for (let i = 0; i < distribution.rent; i += 1) {
      docs.push(createRentListing(i + 1, pickRandom(ownerPools.landlords)));
    }
    for (let i = 0; i < distribution.sale; i += 1) {
      docs.push(createSaleListing(i + 1, pickRandom(ownerPools.brokers)));
    }
    for (let i = 0; i < distribution.lease; i += 1) {
      docs.push(createLeaseListing(i + 1, pickRandom(ownerPools.brokers)));
    }

    // Shuffle for mixed insertion order.
    docs.sort(() => Math.random() - 0.5);

    await commitInBatches(docs);

    console.log("✅ Property seed complete.");
    console.log(`Total created: ${docs.length}`);
    console.log("Distribution:", distribution);
  } catch (error) {
    console.error("❌ Failed to seed properties:", error);
  }
}

// Optional global helper for browser console usage.
window.seedProperties = seedProperties;
