const path = require("node:path");

const cwd = __dirname;
const pythonBin = process.env.PYTHON_BIN || "python";
const configFile = process.env.CONFIG_FILE || "config.toml";
const pm2Cron = process.env.PM2_CRON || "15 13 * * *";
const extraArgs = process.env.RUN_ARGS ? process.env.RUN_ARGS.split(/\s+/).filter(Boolean) : [];

module.exports = {
  apps: [
    {
      name: "daily-arxiv-notify",
      cwd,
      script: pythonBin,
      args: ["-m", "app.cli", "run-once", "--config", configFile, ...extraArgs],
      interpreter: "none",
      exec_mode: "fork",
      autorestart: false,
      max_restarts: 0,
      cron_restart: pm2Cron,
      time: true,
      merge_logs: true,
      out_file: path.join(cwd, "logs", "pm2-out.log"),
      error_file: path.join(cwd, "logs", "pm2-error.log"),
      env: {
        PYTHONUNBUFFERED: "1",
      },
      env_production: {
        NODE_ENV: "production",
        PYTHONUNBUFFERED: "1",
      },
    },
  ],
};
