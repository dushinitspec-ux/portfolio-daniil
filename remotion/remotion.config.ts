import { Config } from "@remotion/cli/config";

Config.setVideoImageFormat("jpeg");
Config.setCodec("h264");
// Flat colours and type compress well; 26 keeps each 40-second video at a few megabytes.
Config.setCrf(26);
