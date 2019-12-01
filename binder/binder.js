require("./node_modules/json-human/css/json.human.css");
require("./node_modules/backgrid/lib/backgrid.min.css");
require("./node_modules/backgrid-paginator/backgrid-paginator.min.css");
require("./node_modules/backgrid-filter/backgrid-filter.min.css");
require("./node_modules/backgrid-grouped-columns/backgrid-grouped-columns.css");
require("./node_modules/backgrid-columnmanager/lib/Backgrid.ColumnManager.css");
require("./mpcontribs-webtzite/webtzite/assets/extra.css");
require("./mpcontribs-webtzite/webtzite/assets/render_json");
require("./mpcontribs-webtzite/webtzite/assets/render_table");
require("./mpcontribs-webtzite/webtzite/assets/render_plot");

const devMode = process.env.NODE_ENV == 'development';
window.api = {'host': devMode ? 'http://localhost:5000/' : 'https://api.mpcontribs.org/'};
