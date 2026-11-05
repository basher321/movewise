// Startup file for the cPanel Node.js app (spec B22).
// The site is built on the PC with "npm run build" (output: "standalone") and uploaded as
// standalone/ next to this file. LiteSpeed/Passenger tells the server where to listen.
process.env.NODE_ENV = "production";
import("./standalone/server.js");
