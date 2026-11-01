var PE_COLORS={living:'#7c5cff',bedroom:'#3d8bfd',kitchen:'#ff8a5b',office:'#2ecc9a',bathroom:'#5ec8e5'};
var PE_MIN=1.5,PE_MAX=15,PE_MAGNET=0.3,PE_MAX_ROOMS=6;
var planEd=null;

function peRound(v){return Math.round(v*10)/10}
function hasPlan(list){return list.length>0&&list.every(function(r){return r.x!=null&&r.y!=null})}
function clearPlan(){rooms.forEach(function(r){delete r.x;delete r.y})}

function peBounds(list){
    var b={x0:Infinity,y0:Infinity,x1:-Infinity,y1:-Infinity};
    list.forEach(function(r){b.x0=Math.min(b.x0,r.x);b.y0=Math.min(b.y0,r.y);b.x1=Math.max(b.x1,r.x+r.w);b.y1=Math.max(b.y1,r.y+r.d)});
    return b;
}

function peOverlaps(i){
    var a=planEd.rooms[i];
    return planEd.rooms.some(function(b,j){
        return j!==i&&overlap(a.x,a.x+a.w,b.x,b.x+b.w)>0.02&&overlap(a.y,a.y+a.d,b.y,b.y+b.d)>0.02;
    });
}

function peDetached(i){
    var a=planEd.rooms[i];
    if(planEd.rooms.length<2)return false;
    return!planEd.rooms.some(function(b,j){
        if(j===i)return false;
        var touchX=Math.abs(a.x+a.w-b.x)<0.01||Math.abs(b.x+b.w-a.x)<0.01,touchY=Math.abs(a.y+a.d-b.y)<0.01||Math.abs(b.y+b.d-a.y)<0.01;
        return touchX&&overlap(a.y,a.y+a.d,b.y,b.y+b.d)>=DOOR_W||touchY&&overlap(a.x,a.x+a.w,b.x,b.x+b.w)>=DOOR_W;
    });
}

function peSnap(value,axis,skip){
    var best=null;
    planEd.rooms.forEach(function(r,j){
        if(j===skip)return;
        (axis==='x'?[r.x,r.x+r.w]:[r.y,r.y+r.d]).forEach(function(edge){
            if(Math.abs(edge-value)<=PE_MAGNET&&(best===null||Math.abs(edge-value)<Math.abs(best-value)))best=edge;
        });
    });
    return best===null?peRound(value):best;
}

function planEditorOpen(){
    var list=rooms.map(function(r){return{type:r.type,zone:r.zone||null,divider:r.divider||null,wishes:r.wishes||'',w:parseFloat(r.width)||3,d:parseFloat(r.length)||3,x:r.x,y:r.y}});
    if(!hasPlan(rooms)){
        var spots=planPackRooms(list.map(function(r){return{room_dimensions:{width:r.w,depth:r.d}}}));
        list.forEach(function(r,i){r.x=spots[i].x;r.y=spots[i].y});
    }
    planEd={rooms:list,sel:0,drag:null,view:null};
    peFitView();
    document.getElementById('plan-editor').hidden=false;
    document.body.style.overflow='hidden';
    peRender();
}

function planEditorClose(){
    document.getElementById('plan-editor').hidden=true;
    document.body.style.overflow='';
    planEd=null;
}

function peFitView(){
    var b=peBounds(planEd.rooms),m=2.5;
    var w=Math.max(b.x1-b.x0+2*m,12),h=Math.max(b.y1-b.y0+2*m,8);
    planEd.view={x:(b.x0+b.x1)/2-w/2,y:(b.y0+b.y1)/2-h/2,w:w,h:h};
}

function peRender(){
    var v=planEd.view,svg=document.getElementById('pe-svg');
    svg.setAttribute('viewBox',[v.x,v.y,v.w,v.h].join(' '));
    var grid='';
    for(var gx=Math.floor(v.x);gx<=v.x+v.w;gx+=0.5)grid+='<line class="pe-grid'+(gx%1===0?' major':'')+'" x1="'+gx+'" y1="'+v.y+'" x2="'+gx+'" y2="'+(v.y+v.h)+'"/>';
    for(var gy=Math.floor(v.y);gy<=v.y+v.h;gy+=0.5)grid+='<line class="pe-grid'+(gy%1===0?' major':'')+'" x1="'+v.x+'" y1="'+gy+'" x2="'+(v.x+v.w)+'" y2="'+gy+'"/>';
    var order=planEd.rooms.map(function(_,i){return i}).filter(function(i){return i!==planEd.sel}).concat([planEd.sel]);
    var body=order.map(function(i){var r=planEd.rooms[i];
        var c=PE_COLORS[r.type]||'#888',bad=peOverlaps(i),sel=i===planEd.sel;
        var name=ROOM_TYPES[r.type]+(r.zone?' '+ZONES[r.zone]:'');
        var g='<g class="pe-room'+(sel?' sel':'')+(bad?' bad':'')+'">'
            +'<rect data-i="'+i+'" data-h="move" x="'+r.x+'" y="'+r.y+'" width="'+r.w+'" height="'+r.d+'" fill="'+c+'" fill-opacity="0.28" stroke="'+(bad?'#ff4d4f':c)+'" stroke-width="0.12"/>'
            +'<text x="'+(r.x+r.w/2)+'" y="'+(r.y+r.d/2-0.1)+'" class="pe-name">'+esc(name)+'</text>'
            +'<text x="'+(r.x+r.w/2)+'" y="'+(r.y+r.d/2+0.4)+'" class="pe-dims">'+peRound(r.w)+' × '+peRound(r.d)+' м · '+(r.w*r.d).toFixed(1)+' м²</text>';
        if(sel){
            var t=0.35;
            g+='<rect class="pe-handle ew" data-i="'+i+'" data-h="l" x="'+(r.x-t/2)+'" y="'+r.y+'" width="'+t+'" height="'+r.d+'"/>'
              +'<rect class="pe-handle ew" data-i="'+i+'" data-h="r" x="'+(r.x+r.w-t/2)+'" y="'+r.y+'" width="'+t+'" height="'+r.d+'"/>'
              +'<rect class="pe-handle ns" data-i="'+i+'" data-h="t" x="'+r.x+'" y="'+(r.y-t/2)+'" width="'+r.w+'" height="'+t+'"/>'
              +'<rect class="pe-handle ns" data-i="'+i+'" data-h="b" x="'+r.x+'" y="'+(r.y+r.d-t/2)+'" width="'+r.w+'" height="'+t+'"/>';
        }
        return g+'</g>';
    }).join('');
    svg.innerHTML=grid+body;
    peSide();
}

function peSide(){
    var r=planEd.rooms[planEd.sel],bad=planEd.rooms.some(function(_,i){return peOverlaps(i)});
    var lone=planEd.rooms.filter(function(_,i){return peDetached(i)}).map(function(x){return ROOM_TYPES[x.type]});
    var list=planEd.rooms.map(function(x,i){
        return'<button type="button" class="pe-item'+(i===planEd.sel?' active':'')+'" onclick="peSelect('+i+')"><span class="pe-dot" style="background:'+(PE_COLORS[x.type]||'#888')+'"></span>'+roomIcon(x.type)+' '+ROOM_TYPES[x.type]+' · '+(x.w*x.d).toFixed(1)+' м²</button>';
    }).join('');
    var opts=Object.keys(ROOM_TYPES).map(function(k){return'<option value="'+k+'"'+(k===r.type?' selected':'')+'>'+ROOM_TYPES[k]+'</option>'}).join('');
    document.getElementById('pe-side').innerHTML='<div class="pe-list">'+list+'</div>'
        +'<button type="button" class="btn-secondary" onclick="peAdd()"'+(planEd.rooms.length>=PE_MAX_ROOMS?' disabled':'')+'>+ Добавить комнату</button>'
        +'<div class="panel"><h4>Выбрана комната</h4><label>Тип</label><select onchange="peSet(\'type\',this.value)">'+opts+'</select>'
        +'<div class="form-row"><div><label>Ширина, м</label><input type="number" step="0.1" min="'+PE_MIN+'" max="'+PE_MAX+'" value="'+peRound(r.w)+'" onchange="peSet(\'w\',this.value)"></div>'
        +'<div><label>Длина, м</label><input type="number" step="0.1" min="'+PE_MIN+'" max="'+PE_MAX+'" value="'+peRound(r.d)+'" onchange="peSet(\'d\',this.value)"></div></div>'
        +'<button type="button" class="btn-danger" onclick="peRemove()"'+(planEd.rooms.length<2?' disabled':'')+'>🗑️ Удалить комнату</button></div>'
        +(bad?'<p class="pe-warn">⚠️ Комнаты наезжают друг на друга — раздвиньте красные.</p>':'')
        +(lone.length?'<p class="pe-note">ℹ️ '+lone.join(', ')+' — не примыкает к другим комнатам, двери в неё не будет. Придвиньте стеной к соседней.</p>':'')
        +'<div class="studio-tools"><button type="button" class="btn-secondary" onclick="planEditorClose()">Отмена</button>'
        +'<button type="button" class="btn-secondary" onclick="peApply(false)"'+(bad?' disabled':'')+'>✅ Применить</button>'
        +'<button type="button" class="btn-primary" onclick="peApply(true)"'+(bad?' disabled':'')+'>Применить и сгенерировать</button></div>';
}

function peSelect(i){planEd.sel=i;peRender()}

function peSet(field,value){
    var r=planEd.rooms[planEd.sel];
    if(field==='type'){r.type=value;if(!ZONES[value]||r.zone===value)r.zone=null}
    else{var n=parseFloat(value);if(n>=PE_MIN&&n<=PE_MAX)r[field]=peRound(n)}
    peRender();
}

function peAdd(){
    if(planEd.rooms.length>=PE_MAX_ROOMS)return;
    var b=peBounds(planEd.rooms);
    planEd.rooms.push({type:'bedroom',zone:null,divider:null,wishes:'',w:3.5,d:3.2,x:peRound(b.x1),y:peRound(b.y0)});
    planEd.sel=planEd.rooms.length-1;
    peFitView();peRender();
}

function peRemove(){
    if(planEd.rooms.length<2)return;
    planEd.rooms.splice(planEd.sel,1);planEd.sel=0;peRender();
}

function pePoint(e){
    var svg=document.getElementById('pe-svg'),pt=svg.createSVGPoint();
    pt.x=e.clientX;pt.y=e.clientY;
    var p=pt.matrixTransform(svg.getScreenCTM().inverse());
    return{x:p.x,y:p.y};
}

function peDown(e){
    var el=e.target,h=el.getAttribute('data-h');
    if(!h)return;
    var i=+el.getAttribute('data-i'),r=planEd.rooms[i];
    planEd.sel=i;
    planEd.drag={i:i,h:h,start:pePoint(e),orig:{x:r.x,y:r.y,w:r.w,d:r.d}};
    document.getElementById('pe-svg').setPointerCapture(e.pointerId);
    e.preventDefault();peRender();
}

function peMove(e){
    var dr=planEd&&planEd.drag;if(!dr)return;
    var p=pePoint(e),dx=p.x-dr.start.x,dy=p.y-dr.start.y,o=dr.orig,r=planEd.rooms[dr.i];
    function clampSize(v){return Math.min(Math.max(v,PE_MIN),PE_MAX)}
    if(dr.h==='move'){
        var x=o.x+dx,y=o.y+dy,sx=peSnap(x,'x',dr.i),sx2=peSnap(x+o.w,'x',dr.i)-o.w,sy=peSnap(y,'y',dr.i),sy2=peSnap(y+o.d,'y',dr.i)-o.d;
        r.x=Math.abs(sx-x)<=Math.abs(sx2-x)?sx:sx2;
        r.y=Math.abs(sy-y)<=Math.abs(sy2-y)?sy:sy2;
    }else if(dr.h==='l'){
        var left=Math.min(peSnap(o.x+dx,'x',dr.i),o.x+o.w-PE_MIN);r.w=clampSize(o.x+o.w-left);r.x=o.x+o.w-r.w;
    }else if(dr.h==='r'){
        r.w=clampSize(peSnap(o.x+o.w+dx,'x',dr.i)-o.x);
    }else if(dr.h==='t'){
        var top=Math.min(peSnap(o.y+dy,'y',dr.i),o.y+o.d-PE_MIN);r.d=clampSize(o.y+o.d-top);r.y=o.y+o.d-r.d;
    }else{
        r.d=clampSize(peSnap(o.y+o.d+dy,'y',dr.i)-o.y);
    }
    r.x=peRound(r.x);r.y=peRound(r.y);r.w=peRound(r.w);r.d=peRound(r.d);
    peRender();
}

function peUp(){
    if(!planEd||!planEd.drag)return;
    planEd.drag=null;
    var b=peBounds(planEd.rooms),v=planEd.view;
    if(b.x0<v.x+0.5||b.y0<v.y+0.5||b.x1>v.x+v.w-0.5||b.y1>v.y+v.h-0.5)peFitView();
    peRender();
}

function peApply(generate){
    if(planEd.rooms.some(function(_,i){return peOverlaps(i)}))return;
    var b=peBounds(planEd.rooms);
    rooms=planEd.rooms.map(function(r){
        return{type:r.type,zone:r.zone,divider:r.divider,wishes:r.wishes,width:peRound(r.w),length:peRound(r.d),x:peRound(r.x-b.x0),y:peRound(r.y-b.y0)};
    });
    planEditorClose();
    document.querySelectorAll('.template-btn').forEach(function(btn){btn.classList.remove('active')});
    renderRooms();
    if(generate)generateAI();
}

document.addEventListener('DOMContentLoaded',function(){
    var svg=document.getElementById('pe-svg');
    if(!svg)return;
    svg.addEventListener('pointerdown',peDown);
    svg.addEventListener('pointermove',peMove);
    svg.addEventListener('pointerup',peUp);
    svg.addEventListener('pointercancel',peUp);
    document.addEventListener('keydown',function(e){if(e.key==='Escape'&&planEd)planEditorClose()});
});
