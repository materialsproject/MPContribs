const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const MiniCssExtractPlugin = require("mini-css-extract-plugin");

module.exports = {
  context: __dirname,
  entry: './assets/js/index',
  output: {
    path: path.resolve('./assets/bundles/'),
    filename: "[name]-[hash].js",
  },
  plugins: [
    new BundleTracker({filename: './webpack-stats.json'}),
    new MiniCssExtractPlugin({ filename: 'style.[contenthash].css', }),
    new webpack.ProvidePlugin({
      _: "underscore", $: "jquery", jquery: "jquery",
      "window.jQuery": "jquery", jQuery:"jquery"
    })
  ],
  resolve: {
    modules: ['node_modules', 'bower_components'],
    extensions: ['.js', '.css'],
    alias: {
      "jquery": 'jquery/dist/jquery',
      "backbone": 'backbone/backbone',
      "backgrid": 'backgrid/lib/backgrid',
      "bootstrap": 'bootstrap/dist/js/bootstrap',
      "filestyle": 'bootstrap-filestyle/src/bootstrap-filestyle',
      "chosen": 'chosen/chosen.jquery',
      "toggle": 'bootstrap-toggle/js/bootstrap-toggle',
      "underscore": 'underscore/underscore',
      "lunr": 'lunr.js/lunr',
      "plotly": 'plotlyjs/plotly',
      "backgrid-select-all": 'backgrid-select-all/backgrid-select-all',
      "backgrid-filter": 'backgrid-filter/backgrid-filter',
      "backbone.paginator": 'backbone.paginator/lib/backbone.paginator',
      "backgrid-paginator": 'backgrid-paginator/backgrid-paginator',
      "backgrid-grouped-columns": 'backgrid-grouped-columns/backgrid-grouped-columns',
      "bootstrap-slider": 'seiyria-bootstrap-slider/dist/bootstrap-slider',
      "json.human": 'json-human/src/json.human',
      "js-cookie": 'js-cookie/src/js.cookie',
      "jquery.spin": 'spin.js/jquery.spin',
      "spin": 'spin.js/spin',
      "linkify": 'linkifyjs/linkify.amd',
      "linkify-element": 'linkifyjs/linkify-element.amd'
      //waitfor: 'jquery.waitFor',
      //thebe: 'main-built',
    }
  },
  module: {
    rules: [
      //{ test: /jquery/, loader: 'exports-loader?jQuery' },
      //{ test: /underscore/, loader: 'exports-loader?_' },
      { test: /backbone/, loader: 'exports-loader?Backbone!imports-loader?underscore,jquery' },
      { test: /backgrid/, loader: 'exports-loader?Backgrid!imports-loader?backbone' },
      { test: /bootstrap/, loader: 'imports-loader?jquery' },
      { test: /filestyle/, loader: 'imports-loader?bootstrap' },
      { test: /chosen/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /toggle/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /backgrid-select-all/, loader: 'imports-loader?backgrid' },
      { test: /backgrid-filter/, loader: 'imports-loader?backgrid' },
      { test: /backbone.paginator/, loader: 'imports-loader?backbone' },
      { test: /backgrid-paginator/, loader: 'imports-loader?backgrid,backbone.paginator' },
      { test: /backgrid-grouped-columns/, loader: 'imports-loader?backgrid' },
      { test: /bootstrap-slider/, loader: 'imports-loader?jquery,bootstrap' },
      { test: /jquery.spin/, loader: 'imports-loader?jquery' },
      { test: /linkify-element/, loader: 'imports-loader?linkify' },
      //{ test: /waitfor/, loader: 'imports-loader?jquery' },
      //{ test: /sandbox/, loader: 'imports-loader?archieml' },
      { test: /\.scss$/, use: ['style-loader', MiniCssExtractPlugin.loader, 'css-loader', 'sass-loader'] },
      { test: /\.(jp(e*)g|png|woff|woff2|eot|ttf|svg)$/, loader: 'url-loader',
        options: { limit: 10000, name: 'images/[hash]-[name].[ext]' } }

    ]
  },
}
