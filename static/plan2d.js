var PLAN_COLORS={
    'диван':'#7b6cd9','кровать':'#5b8def','шкаф':'#a0754f','стеллаж':'#a0754f','тумба':'#a0754f',
    'стол':'#c9a26b','стул':'#9aa5b1','кресло':'#8c7ae6','тв':'#2d3436','гарнитур':'#b08968','холодос':'#dfe6e9','лампа':'#f6c453','ковёр':'#b5838d','ванна':'#e8f1f5','унитаз':'#f5f5f5','раковина':'#d9d9d9','стиралка':'#cfd8dc'
};
var WALL_T=0.12,DOOR_W=0.9;

function overlap(a0,a1,b0,b1){return Math.min(a1,b1)-Math.max(a0,b0)}

function planPackRooms(rooms){
    var spots=rooms.length&&rooms.every(function(r){return r.plan})?rooms.map(function(r){
        return{x:r.plan.x,y:r.plan.y,w:r.room_dimensions.width,d:r.room_dimensions.depth};
    }):packRows(rooms);
    spots.forEach(function(s){
        function neighbour(edge,otherEdge){
            return spots.some(function(o){return o!==s&&overlap(s.x,s.x+s.w,o.x,o.x+o.w)>0.05&&Math.abs(otherEdge(o)-edge)<0.01});
        }
        var topShared=neighbour(s.y,function(o){return o.y+o.d}),bottomShared=neighbour(s.y+s.d,function(o){return o.y});
        s.rot=topShared&&!bottomShared?180:0;
    });
    return spots;
}
function packRows(rooms){
    var total=rooms.reduce(function(s,r){return s+r.room_dimensions.width*r.room_dimensions.depth},0);
    var widest=Math.max.apply(null,rooms.map(function(r){return r.room_dimensions.width}));
    var rowMax=Math.max(widest,Math.sqrt(total)*1.6);
    var order=rooms.map(function(r,i){return i}).sort(function(a,b){
        var A=rooms[a].room_dimensions,B=rooms[b].room_dimensions;return B.width*B.depth-A.width*A.depth});
    var x=0,y=0,rowH=0,spots=[];
    order.forEach(function(i){
        var d=rooms[i].room_dimensions;
        if(x>0&&x+d.width>rowMax+0.01){x=0;y+=rowH;rowH=0}
        spots[i]={x:x,y:y,w:d.width,d:d.depth};
        x+=d.width;rowH=Math.max(rowH,d.depth);
    });
    return spots;
}

function roomTransform(spot){
    var W=spot.w,D=spot.d,flip=spot.rot===180;
    return{
        p:function(x,z){return flip?[spot.x+W-x,spot.y+D-z]:[spot.x+x,spot.y+z]},
        inv:function(px,py){return flip?[spot.x+W-px,spot.y+D-py]:[px-spot.x,py-spot.y]},
        a:flip?180:0
    };
}

var PLAN_EDGE_OF_SIDE={0:{back:'top',front:'bottom',left:'left',right:'right'},180:{back:'bottom',front:'top',left:'right',right:'left'}};

function planEdges(spots,i){
    var s=spots[i],edges={
        top:{horiz:true,at:s.y,lo:s.x,hi:s.x+s.w,n:[0,-1]},bottom:{horiz:true,at:s.y+s.d,lo:s.x,hi:s.x+s.w,n:[0,1]},
        left:{horiz:false,at:s.x,lo:s.y,hi:s.y+s.d,n:[-1,0]},right:{horiz:false,at:s.x+s.w,lo:s.y,hi:s.y+s.d,n:[1,0]}};
    Object.keys(edges).forEach(function(k){
        var e=edges[k],shared=[];
        spots.forEach(function(o,j){
            if(j===i)return;
            var touch=e.horiz?(Math.abs(o.y-e.at)<0.01||Math.abs(o.y+o.d-e.at)<0.01):(Math.abs(o.x-e.at)<0.01||Math.abs(o.x+o.w-e.at)<0.01);
            var a=e.horiz?o.x:o.y,b=e.horiz?o.x+o.w:o.y+o.d;
            if(touch&&overlap(e.lo,e.hi,a,b)>0.05)shared.push([Math.max(e.lo,a),Math.min(e.hi,b),j]);
        });
        shared.sort(function(a,b){return a[0]-b[0]});
        var free=[],cur=e.lo;
        shared.forEach(function(iv){if(iv[0]>cur+0.01)free.push([cur,iv[0]]);cur=Math.max(cur,iv[1])});
        if(e.hi>cur+0.01)free.push([cur,e.hi]);
        e.shared=shared;e.exterior=free;
    });
    return edges;
}

function edgeLine(e,lo,hi,cls){
    return e.horiz?'<line class="'+cls+'" x1="'+lo+'" y1="'+e.at+'" x2="'+hi+'" y2="'+e.at+'"/>':'<line class="'+cls+'" x1="'+e.at+'" y1="'+lo+'" x2="'+e.at+'" y2="'+hi+'"/>';
}

function planEntrance(rooms,spots){
    var order=rooms.map(function(r,i){return i}).filter(function(i){return!isBath(rooms[i])}).sort(function(a,b){
        var la=rooms[a].room_type==='living'?1:0,lb=rooms[b].room_type==='living'?1:0;
        return lb-la||spots[b].w*spots[b].d-spots[a].w*spots[a].d});
    var boxes=planFootprints(rooms,spots);
    function free(cx,cy,w,h){return!boxes.some(function(b){return Math.abs(cx-b.x)<(w+b.w)/2&&Math.abs(cy-b.y)<(h+b.d)/2})}
    for(var oi=0;oi<order.length;oi++){
        var i=order[oi],s=spots[i],edges=planEdges(spots,i),map=PLAN_EDGE_OF_SIDE[s.rot||0];
        var prefer=[map.front,map.left,map.right].concat(rooms.length===1?[]:[map.back]);
        for(var k=0;k<prefer.length;k++){
            var e=edges[prefer[k]];
            for(var v=0;v<e.exterior.length;v++){
                var iv=e.exterior[v],best=null;
                for(var c=iv[0]+DOOR_W/2+0.2;c<=iv[1]-DOOR_W/2-0.2+0.001;c+=0.05){
                    var px=e.horiz?c:e.at,py=e.horiz?e.at:c,ok=e.horiz?free(px,py,DOOR_W,1.6):free(px,py,1.6,DOOR_W);
                    var dist=Math.abs(c-(iv[0]+iv[1])/2);
                    if(ok&&(!best||dist<best.dist))best={c:c,dist:dist};
                }
                if(best)return{room:i,x:e.horiz?best.c:e.at,y:e.horiz?e.at:best.c,horiz:e.horiz,n:[-e.n[0],-e.n[1]]};
            }
        }
    }
    return null;
}

function planEntranceSVG(d){
    var h=DOOR_W/2,t=WALL_T/2+0.01,nx=d.n[0],ny=d.n[1],out='<g class="plan-entrance">';
    if(d.horiz){
        out+='<rect class="plan-door-gap" x="'+(d.x-h)+'" y="'+(d.y-t)+'" width="'+DOOR_W+'" height="'+(t*2)+'"/>';
        out+='<line x1="'+(d.x-h)+'" y1="'+d.y+'" x2="'+(d.x-h)+'" y2="'+(d.y+ny*DOOR_W)+'"/>';
        out+='<path d="M'+(d.x-h)+' '+(d.y+ny*DOOR_W)+' A'+DOOR_W+' '+DOOR_W+' 0 0 '+(ny>0?0:1)+' '+(d.x+h)+' '+d.y+'"/>';
        out+='<text x="'+d.x+'" y="'+(d.y-ny*0.32+0.07)+'">Вход</text>';
    }else{
        out+='<rect class="plan-door-gap" x="'+(d.x-t)+'" y="'+(d.y-h)+'" width="'+(t*2)+'" height="'+DOOR_W+'"/>';
        out+='<line x1="'+d.x+'" y1="'+(d.y-h)+'" x2="'+(d.x+nx*DOOR_W)+'" y2="'+(d.y-h)+'"/>';
        out+='<path d="M'+(d.x+nx*DOOR_W)+' '+(d.y-h)+' A'+DOOR_W+' '+DOOR_W+' 0 0 '+(nx>0?1:0)+' '+d.x+' '+(d.y+h)+'"/>';
        out+='<text x="'+(d.x-nx*0.42)+'" y="'+(d.y+0.07)+'">Вход</text>';
    }
    return out+'<title>Входная дверь</title></g>';
}

function sideOfLocal(x,z,W,D){
    if(z>D)return'front';if(z<0)return'back';if(x<0)return'left';if(x>W)return'right';return null;
}

function studioRoute(rooms){
    var spots=planPackRooms(rooms),entrance=planEntrance(rooms,spots);
    if(!entrance)return null;
    function center(i){return[spots[i].x+spots[i].w/2,spots[i].y+spots[i].d/2]}
    function ext(i,h){return Math.abs(h[0])*spots[i].w/2+Math.abs(h[1])*spots[i].d/2}
    var c0=center(entrance.room),cam0=[entrance.x+entrance.n[0]*0.3,entrance.y+entrance.n[1]*0.3];
    var dx=c0[0]-cam0[0],dy=c0[1]-cam0[1],L=Math.hypot(dx,dy),h=[dx/L,dy/L],margin=L-ext(entrance.room,h);
    function insideApartment(p){
        return spots.some(function(o,j){return!isBath(rooms[j])&&p[0]>o.x+0.2&&p[0]<o.x+o.w-0.2&&p[1]>o.y+0.2&&p[1]<o.y+o.d-0.2});
    }
    var hfov=2*Math.atan(Math.tan(35*Math.PI/180)*PHOTO_SIZE.w/PHOTO_SIZE.h)*180/Math.PI;
    var boxes=planFootprints(rooms,spots),xmax=Math.max.apply(null,spots.map(function(o){return o.x+o.w})),ymax=Math.max.apply(null,spots.map(function(o){return o.y+o.d}));
    function clear(q){return!boxes.some(function(b){return Math.abs(q[0]-b.x)<b.w/2+0.35&&Math.abs(q[1]-b.y)<b.d/2+0.35})}
    var walls=[];
    rooms.forEach(function(r,j){
        var edges=planEdges(spots,j);
        Object.keys(edges).forEach(function(k){
            var e=edges[k],solid=e.exterior.concat(e.shared.filter(function(iv){return isBath(r)!==isBath(rooms[iv[2]])}));
            solid.forEach(function(iv){walls.push(e.horiz?[iv[0],e.at,iv[1],e.at]:[e.at,iv[0],e.at,iv[1]])});
        });
    });
    function crosses(a,b,w){
        function side(p,q,r){return(q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])}
        var c=[w[0],w[1]],d=[w[2],w[3]];
        return side(a,b,c)*side(a,b,d)<0&&side(c,d,a)*side(c,d,b)<0;
    }
    function seen(q,t){return!walls.some(function(w){return crosses(q,t,w)})}
    return rooms.map(function(r,i){
        var c=center(i),p=cam0,t=c;
        if(i!==entrance.room){
            var best=null,want=ext(i,h)+1.2;
            for(var x=0.2;x<xmax;x+=0.1)for(var y=0.2;y<ymax;y+=0.1){
                var q=[x,y];
                if(!insideApartment(q)||!clear(q))continue;
                var vx=c[0]-q[0],vy=c[1]-q[1],dist=Math.hypot(vx,vy);
                if(dist<1.8||!seen(q,c))continue;
                var s=spots[i],corners=[[s.x+0.4,s.y+0.4],[s.x+s.w-0.4,s.y+0.4],[s.x+0.4,s.y+s.d-0.4],[s.x+s.w-0.4,s.y+s.d-0.4]];
                var vis=corners.filter(function(k){return seen(q,k)}).length/4;
                var turn=Math.abs(Math.atan2(vx*h[1]-vy*h[0],vx*h[0]+vy*h[1]));
                var score=4*vis-Math.abs(dist-want)-3*turn;
                if(!best||score>best.score)best={q:q,score:score};
            }
            p=best?best.q:[c[0]-h[0]*want,c[1]-h[1]*want];
        }
        var T=roomTransform(spots[i]),lp=T.inv(p[0],p[1]),lt=T.inv(t[0],t[1]);
        return{x:+lp[0].toFixed(2),z:+lp[1].toFixed(2),tx:+lt[0].toFixed(2),tz:+lt[1].toFixed(2),hfov:+hfov.toFixed(1),side:null,
            plan:{x:p[0],z:p[1],tx:t[0],tz:t[1]}};
    });
}

function planToWorld(li,lx,lz){
    var r=li.pos.rot||0,z=lz+li.shift;
    return{x:li.pos.x+lx*Math.cos(r)+z*Math.sin(r),z:li.pos.z-lx*Math.sin(r)+z*Math.cos(r)};
}

function planRect(T,li,cx,cz,w,d,fill,title,opacity){
    var c=planToWorld(li,cx,cz),p=T.p(c.x,c.z),deg=-(li.pos.rot||0)*180/Math.PI+T.a;
    return'<rect x="'+(p[0]-w/2)+'" y="'+(p[1]-d/2)+'" width="'+w+'" height="'+d+'" rx="0.04" fill="'+fill+'" fill-opacity="'+(opacity||0.88)+'" stroke="#0b0b14" stroke-width="0.02" transform="rotate('+deg+' '+p[0]+' '+p[1]+')"><title>'+title+'</title></rect>';
}

function planLabelSpot(layout,D,bw,bh){
    var m=0.15,cands=[[D.width/2,D.depth-bh/2-m],[D.width/2,bh/2+m],[D.width/2,D.depth/2],
        [bw/2+m,D.depth-bh/2-m],[D.width-bw/2-m,D.depth-bh/2-m],[bw/2+m,bh/2+m],[D.width-bw/2-m,bh/2+m]];
    function free(cx,cy){
        return!layout.items.some(function(li){var p=li.pos;return kindOf(li.item)!=='ковёр'&&Math.abs(cx-p.x)<(bw+p.w)/2&&Math.abs(cy-p.z)<(bh+p.d)/2});
    }
    for(var i=0;i<cands.length;i++)if(free(cands[i][0],cands[i][1]))return cands[i];
    for(var y=bh/2+m;y<=D.depth-bh/2-m;y+=0.1)
        for(var x=bw/2+m;x<=D.width-bw/2-m;x+=0.1)if(free(x,y))return[x,y];
    return null;
}

function planItemLabel(T,li){
    var len=li.dims.w-0.12,max=Math.floor(len/0.1),label=String(li.item.item).split(/\s+/)[0];
    if(max<3||li.dims.d<0.3)return'';
    if(label.length>max)label=label.slice(0,max-1)+'…';
    var c=planToWorld(li,0,0),p=T.p(c.x,c.z),turn=quarter(li.pos.rot)?' transform="rotate(-90 '+p[0]+' '+p[1]+')"':'';
    return'<text class="plan-item-label" x="'+p[0]+'" y="'+(p[1]+0.06)+'"'+turn+'>'+esc(label)+'</text>';
}

function wallSegment(side,W,D){
    return{front:[0,D,W,D],back:[0,0,W,0],left:[0,0,0,D],right:[W,0,W,D]}[side];
}

function clipToRect(poly,r){
    var edges=[[function(p){return p[0]>=r.x0},function(a,b){var t=(r.x0-a[0])/(b[0]-a[0]);return[r.x0,a[1]+t*(b[1]-a[1])]}],
        [function(p){return p[0]<=r.x1},function(a,b){var t=(r.x1-a[0])/(b[0]-a[0]);return[r.x1,a[1]+t*(b[1]-a[1])]}],
        [function(p){return p[1]>=r.y0},function(a,b){var t=(r.y0-a[1])/(b[1]-a[1]);return[a[0]+t*(b[0]-a[0]),r.y0]}],
        [function(p){return p[1]<=r.y1},function(a,b){var t=(r.y1-a[1])/(b[1]-a[1]);return[a[0]+t*(b[0]-a[0]),r.y1]}]];
    edges.forEach(function(e){
        var inside=e[0],cut=e[1],res=[];
        poly.forEach(function(cur,i){
            var prev=poly[(i+poly.length-1)%poly.length];
            if(inside(cur)){if(!inside(prev))res.push(cut(prev,cur));res.push(cur)}
            else if(inside(prev))res.push(cut(prev,cur));
        });
        poly=res;
    });
    return poly;
}

function planCameraSVG(T,cam,W,D,showHidden,clip){
    var out='';
    if(showHidden&&cam.side){
        var s=wallSegment(cam.side,W,D),a=T.p(s[0],s[1]),b=T.p(s[2],s[3]);
        out+='<line class="plan-hidden-wall" x1="'+a[0]+'" y1="'+a[1]+'" x2="'+b[0]+'" y2="'+b[1]+'"/>';
    }
    var c=T.p(cam.x,cam.z),t=T.p(cam.tx,cam.tz),ang=Math.atan2(t[1]-c[1],t[0]-c[0]),half=cam.hfov*Math.PI/360;
    var len=Math.min(Math.hypot(t[0]-c[0],t[1]-c[1])*1.9,Math.hypot(W,D)+1.5);
    var cone=[c];
    for(var k=0;k<=16;k++){var a=ang-half+2*half*k/16;cone.push([c[0]+Math.cos(a)*len,c[1]+Math.sin(a)*len])}
    if(clip)cone=clipToRect(cone,clip);
    if(cone.length>2)out+='<polygon class="plan-cam-cone" points="'+cone.map(function(p){return p[0].toFixed(3)+','+p[1].toFixed(3)}).join(' ')+'"/>';
    out+='<line class="plan-cam-axis" x1="'+c[0]+'" y1="'+c[1]+'" x2="'+t[0]+'" y2="'+t[1]+'"/>';
    out+='<g transform="translate('+c[0]+' '+c[1]+') rotate('+(ang*180/Math.PI)+')"><rect class="plan-cam-body" x="-0.32" y="-0.16" width="0.34" height="0.32" rx="0.05"/><path class="plan-cam-body" d="M0.02 -0.08 L0.2 -0.16 L0.2 0.16 L0.02 0.08 Z"/></g>';
    out+='<title>Камера: высота 1.6 м, угол обзора '+Math.round(cam.hfov)+'°'+(cam.side?', стена убрана на время съёмки':'')+'</title>';
    return'<g class="plan-cam">'+out+'</g>';
}

function planRoomSVG(room,spot,idx,opts){
    var D=room.room_dimensions,layout=computeLayout(room.furniture,D,room.room_type),T=roomTransform(spot),out='';
    var o=T.p(0,0),e=T.p(D.width,D.depth),x0=Math.min(o[0],e[0]),y0=Math.min(o[1],e[1]);
    out+='<g class="plan-room" data-room="'+idx+'">';
    out+='<rect class="plan-floor" x="'+x0+'" y="'+y0+'" width="'+D.width+'" height="'+D.depth+'"/>';
    if(layout.decor){
        var w0=T.p(layout.decor.winX-0.7,0),w1=T.p(layout.decor.winX+0.7,0);
        out+='<line class="plan-window" x1="'+w0[0]+'" y1="'+w0[1]+'" x2="'+w1[0]+'" y2="'+w1[1]+'" stroke-width="'+(WALL_T+0.04)+'"><title>Окно</title></line>';
    }
    layout.items.slice().sort(function(a,b){return(kindOf(b.item)==='ковёр')-(kindOf(a.item)==='ковёр')}).forEach(function(li){
        var it=li.item,k=kindOf(it),fill=PLAN_COLORS[k]||'#8a2be2';
        out+=planRect(T,li,0,0,li.dims.w,k==='тв'?Math.max(li.dims.d,0.42):li.dims.d,fill,esc(it.item)+' · '+esc(it.dimensions||''),k==='ковёр'?0.4:0.88);
        chairSpots(it,li.dims,room.room_type).forEach(function(sp){out+=planRect(T,li,sp.x,sp.z,0.42,0.42,PLAN_COLORS['стул'],'Стул')});
        out+=planItemLabel(T,li);
    });
    if(!opts||opts.walls!==false)out+='<rect class="plan-wall" x="'+x0+'" y="'+y0+'" width="'+D.width+'" height="'+D.depth+'" stroke-width="'+WALL_T+'"/>';
    if(opts&&opts.camera)out+=planCameraSVG(T,roomCamera(room),D.width,D.depth,opts.hiddenWall);
    if(!opts||opts.label!==false){
        var size=D.width+' × '+D.depth+' м · '+room.area+' м²';
        var bw=Math.max(room.room_name.length*0.19,size.length*0.115)+0.3,bh=0.66,spotL=planLabelSpot(layout,D,bw,bh),full=!!spotL;
        if(!full){
            bw=room.room_name.length*0.19+0.3;bh=0.42;
            spotL=planLabelSpot(layout,D,bw,bh)||[D.width/2,D.depth-bh/2-0.15];
        }
        var lp=T.p(spotL[0],spotL[1]);
        out+='<rect class="plan-label-bg" x="'+(lp[0]-bw/2)+'" y="'+(lp[1]-bh/2)+'" width="'+bw+'" height="'+bh+'" rx="0.1"><title>'+size+'</title></rect>';
        if(full){
            out+='<text class="plan-room-name" x="'+lp[0]+'" y="'+(lp[1]-0.03)+'">'+esc(room.room_name)+'</text>';
            out+='<text class="plan-room-size" x="'+lp[0]+'" y="'+(lp[1]+0.22)+'">'+size+'</text>';
        }else{
            out+='<text class="plan-room-name" x="'+lp[0]+'" y="'+(lp[1]+0.1)+'">'+esc(room.room_name)+'</text>';
        }
    }
    out+='</g>';
    return out;
}

function planFootprints(rooms,spots){
    var boxes=[];
    rooms.forEach(function(room,i){
        var T=roomTransform(spots[i]),layout=computeLayout(room.furniture,room.room_dimensions,room.room_type);
        layout.items.forEach(function(li){if(kindOf(li.item)==='ковёр')return;var p=T.p(li.pos.x,li.pos.z);boxes.push({x:p[0],y:p[1],w:li.pos.w,d:li.pos.d})});
    });
    return boxes;
}

function isBath(room){return room.room_type==='bathroom'}

function planDoors(rooms,spots,openPlan){
    var boxes=planFootprints(rooms,spots),doors=[];
    function free(cx,cy,w,h){return!boxes.some(function(b){return Math.abs(cx-b.x)<(w+b.w)/2&&Math.abs(cy-b.y)<(h+b.d)/2})}
    for(var i=0;i<spots.length;i++)for(var j=i+1;j<spots.length;j++){
        var a=spots[i],b=spots[j],horiz=null,from,to,at;
        if(Math.abs(a.y+a.d-b.y)<0.01||Math.abs(b.y+b.d-a.y)<0.01){
            horiz=true;at=Math.abs(a.y+a.d-b.y)<0.01?b.y:a.y;from=Math.max(a.x,b.x);to=Math.min(a.x+a.w,b.x+b.w);
        }else if(Math.abs(a.x+a.w-b.x)<0.01||Math.abs(b.x+b.w-a.x)<0.01){
            horiz=false;at=Math.abs(a.x+a.w-b.x)<0.01?b.x:a.x;from=Math.max(a.y,b.y);to=Math.min(a.y+a.d,b.y+b.d);
        }
        if(horiz===null||to-from<DOOR_W+0.3)continue;
        if(openPlan&&!isBath(rooms[i])&&!isBath(rooms[j]))continue;
        var best=null;
        for(var c=from+DOOR_W/2+0.15;c<=to-DOOR_W/2-0.15+0.001;c+=0.05){
            var ok=horiz?free(c,at,DOOR_W,1.6):free(at,c,1.6,DOOR_W),dist=Math.abs(c-(from+to)/2);
            if(ok&&(!best||dist<best.dist))best={c:c,dist:dist};
        }
        var pos=best?best.c:(from+to)/2;
        doors.push(horiz?{x:pos,y:at,horiz:true}:{x:at,y:pos,horiz:false});
    }
    return doors;
}

function planDoorSVG(d){
    var h=DOOR_W/2,t=WALL_T/2+0.01;
    if(d.horiz){
        return'<g class="plan-door"><rect class="plan-door-gap" x="'+(d.x-h)+'" y="'+(d.y-t)+'" width="'+DOOR_W+'" height="'+(t*2)+'"/>'
            +'<line x1="'+(d.x-h)+'" y1="'+d.y+'" x2="'+(d.x-h)+'" y2="'+(d.y+DOOR_W)+'"/>'
            +'<path d="M'+(d.x-h)+' '+(d.y+DOOR_W)+' A'+DOOR_W+' '+DOOR_W+' 0 0 0 '+(d.x+h)+' '+d.y+'"/><title>Дверь</title></g>';
    }
    return'<g class="plan-door"><rect class="plan-door-gap" x="'+(d.x-t)+'" y="'+(d.y-h)+'" width="'+(t*2)+'" height="'+DOOR_W+'"/>'
        +'<line x1="'+d.x+'" y1="'+(d.y-h)+'" x2="'+(d.x+DOOR_W)+'" y2="'+(d.y-h)+'"/>'
        +'<path d="M'+(d.x+DOOR_W)+' '+(d.y-h)+' A'+DOOR_W+' '+DOOR_W+' 0 0 1 '+d.x+' '+(d.y+h)+'"/><title>Дверь</title></g>';
}

function roomPlanContext(rooms,i,openPlan){
    var spots=planPackRooms(rooms),s=spots[i],T=roomTransform(s),W=s.w,D=s.d,ctx={exterior:[],doors:[]};
    var doors=planDoors(rooms,spots,openPlan);
    ['front','back','left','right'].forEach(function(side){
        var seg=wallSegment(side,W,D),a=T.p(seg[0],seg[1]),b=T.p(seg[2],seg[3]);
        var horiz=Math.abs(a[1]-b[1])<0.01,at=horiz?a[1]:a[0],lo=horiz?Math.min(a[0],b[0]):Math.min(a[1],b[1]),hi=horiz?Math.max(a[0],b[0]):Math.max(a[1],b[1]);
        var shared=spots.some(function(o,j){
            if(j===i)return false;
            if(horiz)return overlap(lo,hi,o.x,o.x+o.w)>0.05&&(Math.abs(o.y-at)<0.01||Math.abs(o.y+o.d-at)<0.01);
            return overlap(lo,hi,o.y,o.y+o.d)>0.05&&(Math.abs(o.x-at)<0.01||Math.abs(o.x+o.w-at)<0.01);
        });
        if(!shared)ctx.exterior.push(side);
        doors.forEach(function(d){
            if(d.horiz!==horiz)return;
            var along=horiz?d.x:d.y,on=horiz?Math.abs(d.y-at)<0.01:Math.abs(d.x-at)<0.01;
            if(!on||along<lo-0.01||along>hi+0.01)return;
            var a0=horiz?a[0]:a[1],b0=horiz?b[0]:b[1],t=(along-a0)/(b0-a0);
            ctx.doors.push({side:side,x:seg[0]+(seg[2]-seg[0])*t,z:seg[1]+(seg[3]-seg[1])*t});
        });
    });
    return ctx;
}

function renderPlan2D(container,rooms,onPick,opts){
    var spots=planPackRooms(rooms),W=0,H=0,body='',pad=0.4,cams='',camPts=[];
    rooms.forEach(function(r,i){
        var s=spots[i];
        W=Math.max(W,s.x+s.w);H=Math.max(H,s.y+s.d);
        body+=planRoomSVG(r,s,i,{camera:false,walls:false});
        if(opts&&opts.cameras&&r.image_source==='3d'){
            var cam=roomCamera(r),T=roomTransform(s);
            camPts.push(T.p(cam.x,cam.z));
            cams+=planCameraSVG(T,cam,s.w,s.d,true,{x0:s.x,y0:s.y,x1:s.x+s.w,y1:s.y+s.d});
        }
    });
    var walls='';
    rooms.forEach(function(r,i){
        var edges=planEdges(spots,i);
        Object.keys(edges).forEach(function(k){
            var e=edges[k];
            e.exterior.forEach(function(iv){walls+=edgeLine(e,iv[0],iv[1],'plan-wall-line')});
            e.shared.forEach(function(iv){
                var zone=opts&&opts.openPlan&&!isBath(r)&&!isBath(rooms[iv[2]]);
                walls+=edgeLine(e,iv[0],iv[1],zone?'plan-zone':'plan-wall-line');
            });
        });
    });
    body+=walls;
    planDoors(rooms,spots,opts&&opts.openPlan).forEach(function(d){body+=planDoorSVG(d)});
    var entrance=planEntrance(rooms,spots);
    if(entrance)body+=planEntranceSVG(entrance);
    var x0=-pad,y0=-pad,x1=W+pad,y1=H+pad;
    camPts.forEach(function(p){x0=Math.min(x0,p[0]-pad);y0=Math.min(y0,p[1]-pad);x1=Math.max(x1,p[0]+pad);y1=Math.max(y1,p[1]+pad)});
    container.innerHTML='<svg class="plan-svg" viewBox="'+x0+' '+y0+' '+(x1-x0)+' '+(y1-y0)+'" role="img" aria-label="План квартиры">'+body+cams+'</svg>';
    container.querySelectorAll('.plan-room').forEach(function(g){
        g.addEventListener('click',function(){onPick(parseInt(g.getAttribute('data-room'),10))});
    });
}

function renderCameraSchema(container,room){
    var D=room.room_dimensions,spot={x:0,y:0,w:D.width,d:D.depth,rot:0},cam=roomCamera(room),pad=0.5;
    var x0=Math.min(0,cam.x)-pad,y0=Math.min(0,cam.z)-pad,x1=Math.max(D.width,cam.x)+pad,y1=Math.max(D.depth,cam.z)+pad;
    container.innerHTML='<svg class="plan-svg cam-schema" viewBox="'+x0+' '+y0+' '+(x1-x0)+' '+(y1-y0)+'" role="img" aria-label="Схема съёмки">'
        +planRoomSVG(room,spot,0,{camera:true,hiddenWall:true,label:false})+'</svg>';
}
