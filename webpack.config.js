const path = require("path");
const webpack = require('webpack');
const BundleTracker = require('webpack-bundle-tracker');
const CleanWebpackPlugin = require("clean-webpack-plugin");
//const MiniCssExtractPlugin = require("mini-css-extract-plugin");
//const BundleAnalyzerPlugin = require('webpack-bundle-analyzer').BundleAnalyzerPlugin;
const devMode = process.env.NODE_ENV !== 'production'
console.log('devMode = ' + devMode)

module.exports = {
  context: __dirname,
  entry: {
    'main': './mpcontribs-webtzite/webtzite/assets/index',
    'portal': './mpcontribs-portal/mpcontribs/portal/assets/index',
    'explorer': './mpcontribs-explorer/mpcontribs/explorer/assets/index',
  },
  output: {
    path: path.resolve(__dirname, 'dist'),
    filename: "[name].[hash].js",
    chunkFilename: '[id].[hash].js',
    crossOriginLoading: "anonymous",
    publicPath: '/static/'
  },
  plugins: [
    //new BundleAnalyzerPlugin(),
    new BundleTracker({filename: './webpack-stats.json'}),
    new CleanWebpackPlugin(["dist"]),
    //new MiniCssExtractPlugin({
    //  filename: "[name].[hash].css",
    //  chunkFilename: "[id].[hash].css",
    //}),
    new webpack.ProvidePlugin({
      _: "underscore", $: "jquery", jquery: "jquery",
      "window.jQuery": "jquery", jQuery:"jquery"
    }),
  ],
  optimization: {
    splitChunks: {
      cacheGroups: {
        styles: {
          name: 'styles',
          test: /\.css$/,
          chunks: 'all',
          enforce: true
        }
      }
    }
  },
  resolve: {
    modules: ['node_modules'],
    extensions: ['.js'],
    alias: {
      "jquery": 'jquery/dist/jquery',
      "bootstrap": 'bootstrap/dist/js/bootstrap',
      "backbone": 'backbone/backbone',
      "backgrid": 'backgrid/lib/backgrid',
      "filestyle": 'bootstrap-filestyle/src/bootstrap-filestyle',
      "chosen": 'chosen-js/chosen.jquery',
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
      { test: /backgrid/, loader: 'imports-loader?backbone' },
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
      { test: /\.(jp(e*)g|png)$/, loader: 'url-loader', options: { limit: 1, name: '[name].[ext]' } },
      { test: /\.css$/, loaders: ["style-loader","css-loader"] },
      {
        test: /\.(woff(2)?|ttf|eot|svg)(\?v=[0-9]\.[0-9]\.[0-9])?$/, loader: 'url-loader',
        options: { limit: 8192, name:'[name].[ext]', outputPath: 'assets' }
      }
    ]
  },
  mode : devMode ? 'development' : 'production'
}
