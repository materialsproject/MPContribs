import img from './logo.png'

import("../../../node_modules/bootstrap/dist/css/bootstrap.min.css");
import("../../../node_modules/bootstrap/dist/css/bootstrap-theme.min.css");
import("../../../node_modules/bootstrap-slider/dist/css/bootstrap-slider.min.css");
import("../../../node_modules/bootstrap-toggle/css/bootstrap-toggle.min.css");
import("../../../node_modules/backgrid/lib/backgrid.min.css");
import("../../../node_modules/backgrid-paginator/backgrid-paginator.min.css");
import("../../../node_modules/backgrid-filter/backgrid-filter.min.css");
import("../../../node_modules/backgrid-grouped-columns/backgrid-grouped-columns.css");
import("../../../node_modules/json-human/css/json.human.css");
import("../../../node_modules/chosen-js/chosen.min.css");
import("../../../node_modules/select2/dist/css/select2.min.css");
import("./extra.css");

function importAll(r) { return r.keys().map(r); }
importAll(require.context('../../../node_modules/chosen-js', true, /\.(png|jpe?g|svg)$/));
import("./Symbola.ttf.svg");

import 'webpack-icons-installer';

window.tables = [];
document.getElementById("logo").src = img;
