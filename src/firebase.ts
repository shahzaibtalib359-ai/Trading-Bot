import { initializeApp } from "firebase/app";
import { getFirestore } from "firebase/firestore";

const firebaseConfig = {
  apiKey: "AIzaSyCcfRWUCWahM0Ra_67iyvMD9oz9USZP2Po",
  authDomain: "trading-by-shahzaib.firebaseapp.com",
  projectId: "trading-by-shahzaib",
  storageBucket: "trading-by-shahzaib.firebasestorage.app",
  messagingSenderId: "1045673450510",
  appId: "1:1045673450510:web:85b674c41254ed11d2f05f",
  measurementId: "G-JM71B1KLW1"
};

// Initialize Firebase
const app = initializeApp(firebaseConfig);

// Initialize Cloud Firestore and export it
export const db = getFirestore(app);
export default app;
