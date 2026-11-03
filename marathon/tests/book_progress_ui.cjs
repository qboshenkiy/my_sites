const fs=require('fs'),vm=require('vm'),assert=require('assert');
const source=fs.readFileSync(require('path').join(__dirname,'../assets/v3.js'),'utf8').split('function weeklyCard')[0];
const context={esc:s=>String(s).replaceAll('&','&amp;').replaceAll('<','&lt;').replaceAll('>','&gt;')};vm.createContext(context);vm.runInContext(source,context);
const w={bookProgress:{label:'Числа · глава 8',next:'Числа · глава 9',books:[{title:'Левит',chapter_from:1,chapter_to:27,through:27,read:27,total:27,done:true},{title:'Числа',chapter_from:1,chapter_to:36,through:8,read:8,total:36,done:false}]}};
const html=context.bookProgressView(w);
assert(html.includes('Левит')&&html.includes('Числа'));assert(html.includes('27 <small>/ 27 гл.'));assert(html.includes('8 <small>/ 36 гл.'));assert(html.includes('max="36" value="8"'));assert(!html.includes('/ 63'));
w.bookProgress.books[1].title='<script>bad()</script>';assert(!context.bookProgressView(w).includes('<script>'));
assert.equal(context.bookProgressView({}), '');
console.log('PASS: separate book chapter counters, progress ranges, hidden cumulative sum and escaped titles');
