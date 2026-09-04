export interface Dish {
  id: string; name: string; emoji: string; price: number; mrp: number; // paise
  restaurant: string; rating: number; time: string; veg: boolean;
  category: string; image: string;
}

const img = (id: string) => `https://images.unsplash.com/${id}?auto=format&fit=crop&w=640&q=60`;

export const DISHES: Dish[] = [
  { id: "d1", name: "Butter Chicken + 2 Naan", emoji: "🍛", price: 34900, mrp: 42900, restaurant: "Punjabi Tadka", rating: 4.5, time: "25 min", veg: false, category: "North Indian", image: img("photo-1603894584373-5ac82b2ae398") },
  { id: "d2", name: "Paneer Tikka Pizza", emoji: "🍕", price: 29900, mrp: 39900, restaurant: "Slice of Italy", rating: 4.3, time: "30 min", veg: true, category: "Pizza", image: img("photo-1513104890138-7c749659a591") },
  { id: "d3", name: "Hyderabadi Chicken Biryani", emoji: "🍗", price: 39900, mrp: 46900, restaurant: "Biryani Blues", rating: 4.7, time: "35 min", veg: false, category: "Biryani", image: img("photo-1589302168068-964664d93dc0") },
  { id: "d4", name: "Masala Dosa + Filter Coffee", emoji: "🥞", price: 18900, mrp: 22900, restaurant: "Udupi Palace", rating: 4.4, time: "20 min", veg: true, category: "South Indian", image: img("photo-1589301760014-d929f3979dbc") },
  { id: "d5", name: "Double Cheese Burger Meal", emoji: "🍔", price: 24900, mrp: 32900, restaurant: "Burger Adda", rating: 4.1, time: "22 min", veg: false, category: "Burgers", image: img("photo-1568901346375-23c9450c58cd") },
  { id: "d6", name: "Chole Bhature", emoji: "🫓", price: 15900, mrp: 19900, restaurant: "Punjabi Tadka", rating: 4.6, time: "25 min", veg: true, category: "North Indian", image: img("photo-1601050690597-df0568f70950") },
  { id: "d7", name: "Sushi Platter (12 pc)", emoji: "🍣", price: 79900, mrp: 99900, restaurant: "Tokyo Bowl", rating: 4.8, time: "40 min", veg: false, category: "Asian", image: img("photo-1579584425555-c3ce17fd4351") },
  { id: "d8", name: "Death by Chocolate Sundae", emoji: "🍨", price: 21900, mrp: 26900, restaurant: "Creamy Dreams", rating: 4.9, time: "15 min", veg: true, category: "Desserts", image: img("photo-1563805042-7684c019e1cb") },
];

export const CATEGORIES = ["All", ...new Set(DISHES.map((d) => d.category))];

export const GOLD_PLAN = { name: "Tomato Gold", price: 49900, period: "month", perks: ["Free delivery on every order", "10% off at 500+ restaurants", "Priority support"] };
